"""Chunk embedding storage and semantic reranking.

Vectors are stored per (chunk text hash, model), not per chunk id. The
post-commit hook reindexes on every commit, which rewrites every chunk row, so
anything keyed on a row id would be thrown away and recomputed each time.
Content addressing makes the cache survive reindexing, share one vector
between documents that repeat a section, and re-embed exactly what changed.

Every entry point degrades instead of failing: a model server that is down
leaves the wiki searchable through BM25.
"""

import math
import sqlite3
from array import array
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path
from typing import Final

from llm_wiki.embedding import EmbeddingProvider
from llm_wiki.errors import EmbeddingBackendError
from llm_wiki.models import EmbedResult
from llm_wiki.store import initialize

VECTOR_TYPECODE: Final = "f"
EMBED_BATCH: Final = 64

type SemanticSearch = Callable[[], list[tuple[int, float]]]

# How many documents the vector side contributes to the candidate pool.
SEMANTIC_CANDIDATES: Final = 20


def embed_missing_chunks(
    db_path: Path,
    provider: EmbeddingProvider,
    model: str,
) -> EmbedResult:
    """Embed every stored chunk that has no vector for this model yet.

    Chunks whose text is unchanged since the last run are counted as reused and
    never sent to the model server, which is what keeps a per-commit reindex
    from re-embedding the whole wiki.
    """
    initialize(db_path)
    pending = _pending_chunks(db_path, model)
    reused = _chunk_total(db_path) - len(pending)
    if not pending:
        return EmbedResult(embedded=0, reused=reused, failed=0, reason=None)

    hashes = list(pending)
    texts = [pending[content_hash] for content_hash in hashes]
    embedded = 0
    for start in range(0, len(texts), EMBED_BATCH):
        batch_hashes = hashes[start : start + EMBED_BATCH]
        try:
            vectors = provider.embed(texts[start : start + EMBED_BATCH])
        except (EmbeddingBackendError, OSError) as exc:
            return _give_up(embedded, reused, len(texts), str(exc))
        if len(vectors) != len(batch_hashes):
            reason = str(
                EmbeddingBackendError.count_mismatch(len(batch_hashes), len(vectors))
            )
            return _give_up(embedded, reused, len(texts), reason)
        _store_vectors(db_path, model, list(zip(batch_hashes, vectors, strict=True)))
        embedded += len(batch_hashes)
    return EmbedResult(embedded=embedded, reused=reused, failed=0, reason=None)


def _give_up(embedded: int, reused: int, total: int, reason: str) -> EmbedResult:
    """Report a partially completed embedding run without raising."""
    return EmbedResult(
        embedded=embedded,
        reused=reused,
        failed=total - embedded,
        reason=reason,
    )


def prune_orphan_embeddings(db_path: Path) -> int:
    """Drop cached vectors whose chunk text no longer appears in any document."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.execute(
            """
            DELETE FROM chunk_embeddings
            WHERE content_hash NOT IN (SELECT content_hash FROM document_chunks)
            """
        )
        connection.commit()
        return max(0, cursor.rowcount)


def has_embeddings(db_path: Path, model: str) -> bool:
    """Report whether any vector is cached for this model."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        row = connection.execute(
            "SELECT 1 FROM chunk_embeddings WHERE model = ? LIMIT 1",
            (model,),
        ).fetchone()
    return row is not None


def make_semantic_search(
    db_path: Path,
    query: str,
    provider: EmbeddingProvider,
    model: str,
    limit: int = SEMANTIC_CANDIDATES,
) -> SemanticSearch | None:
    """Build a whole-wiki vector search for one query, or None if unavailable.

    Returns None — never raises — when nothing has been embedded yet or the
    model server refuses the query, so the caller keeps its BM25 ordering. The
    stored-vector check comes first so a BM25-only wiki never pays for an HTTP
    round trip.

    The search itself contributes its *own* candidates rather than reordering
    the lexical ones. Reranking alone would never surface a document that
    shares no words with the query, which is the entire reason to embed.
    """
    if query.strip() == "" or not has_embeddings(db_path, model):
        return None
    try:
        vectors = provider.embed([query])
    except (EmbeddingBackendError, OSError):
        return None
    if len(vectors) != 1:
        return None
    query_vector = tuple(float(value) for value in vectors[0])
    query_norm = math.sqrt(sum(value * value for value in query_vector))
    if query_norm == 0.0:
        return None

    def run() -> list[tuple[int, float]]:
        scored = _score_documents(db_path, model, query_vector, query_norm)
        ranked = sorted(scored.items(), key=lambda item: -item[1])
        return [(document_id, score) for document_id, score in ranked if score > 0][
            :limit
        ]

    return run


def _score_documents(
    db_path: Path,
    model: str,
    query_vector: tuple[float, ...],
    query_norm: float,
) -> dict[int, float]:
    """Score every document by its best-matching chunk's cosine similarity.

    A full scan in Python is deliberate: at this project's stated scale — about
    5000 chunks for a 1000-document wiki — it costs milliseconds, and it keeps
    the database a plain SQLite file with no vector-index extension to install.
    A wiki large enough to feel this is a wiki that needs a different store.
    """
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT c.document_id, e.vector
            FROM document_chunks c
            JOIN chunk_embeddings e ON e.content_hash = c.content_hash
            WHERE e.model = ?
            """,
            (model,),
        ).fetchall()

    best: dict[int, float] = {}
    for document_id, blob in rows:
        score = _cosine(query_vector, query_norm, _decode(blob))
        if score > best.get(int(document_id), float("-inf")):
            best[int(document_id)] = score
    return best


def _cosine(
    query_vector: tuple[float, ...],
    query_norm: float,
    vector: tuple[float, ...],
) -> float:
    """Cosine similarity, treating a width mismatch as no similarity.

    A stored vector of the wrong width means the model changed under a reused
    name; scoring it as zero degrades ranking instead of corrupting it.
    """
    if len(vector) != len(query_vector):
        return 0.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return 0.0
    dot = sum(a * b for a, b in zip(query_vector, vector, strict=True))
    return dot / (query_norm * norm)


def _pending_chunks(db_path: Path, model: str) -> dict[str, str]:
    """Map content hash to text for every chunk lacking a vector, deduplicated."""
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT c.content_hash, c.text
            FROM document_chunks c
            WHERE NOT EXISTS (
                SELECT 1 FROM chunk_embeddings e
                WHERE e.content_hash = c.content_hash AND e.model = ?
            )
            """,
            (model,),
        ).fetchall()
    return {str(content_hash): str(text) for content_hash, text in rows}


def _chunk_total(db_path: Path) -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        row = connection.execute(
            "SELECT COUNT(DISTINCT content_hash) FROM document_chunks"
        ).fetchone()
    return int(row[0]) if row else 0


def _store_vectors(
    db_path: Path,
    model: str,
    pairs: Sequence[tuple[str, Sequence[float]]],
) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        for content_hash, vector in pairs:
            encoded = _encode(vector)
            _ = connection.execute(
                """
                INSERT INTO chunk_embeddings (content_hash, model, dimension, vector)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(content_hash, model) DO UPDATE SET
                    dimension = excluded.dimension,
                    vector = excluded.vector
                """,
                (content_hash, model, len(vector), encoded),
            )
        connection.commit()


def _encode(vector: Sequence[float]) -> bytes:
    """Pack a vector as float32.

    Half the size of float64 and below the noise floor of embedding similarity,
    and the database is only ever read on the machine that wrote it.
    """
    return array(VECTOR_TYPECODE, [float(value) for value in vector]).tobytes()


def _decode(blob: object) -> tuple[float, ...]:
    if not isinstance(blob, bytes):
        return ()
    values = array(VECTOR_TYPECODE)
    values.frombytes(blob)
    return tuple(values)


__all__ = [
    "EMBED_BATCH",
    "SEMANTIC_CANDIDATES",
    "SemanticSearch",
    "embed_missing_chunks",
    "has_embeddings",
    "make_semantic_search",
    "prune_orphan_embeddings",
]
