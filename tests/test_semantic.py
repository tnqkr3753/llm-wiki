"""Tests for incremental chunk embedding and hybrid retrieval."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from llm_wiki.models import ParsedDocument
from llm_wiki.semantic import (
    embed_missing_chunks,
    has_embeddings,
    make_semantic_search,
    prune_orphan_embeddings,
)
from llm_wiki.store import search, upsert_document

MODEL = "test-model"


class _CountingProvider:
    """Embed deterministically from token overlap, counting every text seen."""

    def __init__(self, vocabulary: Sequence[str]) -> None:
        self.vocabulary = tuple(vocabulary)
        self.seen: list[str] = []

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.seen.extend(texts)
        return tuple(self._vector(text) for text in texts)

    def _vector(self, text: str) -> tuple[float, ...]:
        lowered = text.lower()
        return tuple(1.0 if word in lowered else 0.0 for word in self.vocabulary)


def _doc(path: str, title: str, body: str) -> ParsedDocument:
    return ParsedDocument(path=path, title=title, tags=(), body=body)


def _stored_vectors(db_path: Path) -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        row = connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()
    return int(row[0])


def test_embedding_covers_every_chunk_once(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha\n\n# Two\n\nbeta"))
    provider = _CountingProvider(["alpha", "beta"])

    result = embed_missing_chunks(db_path, provider, MODEL)

    assert result.embedded == 2
    assert result.reused == 0
    assert _stored_vectors(db_path) == 2


def test_an_unchanged_chunk_is_never_re_embedded(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha\n\n# Two\n\nbeta"))
    provider = _CountingProvider(["alpha", "beta"])
    _ = embed_missing_chunks(db_path, provider, MODEL)

    _ = upsert_document(
        db_path, _doc("/a.md", "A", "# One\n\nalpha\n\n# Two\n\nbeta changed")
    )
    provider.seen.clear()
    result = embed_missing_chunks(db_path, provider, MODEL)

    assert result.embedded == 1
    assert result.reused == 1
    assert all("alpha" not in text for text in provider.seen)


def test_a_different_model_embeds_independently(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha"))
    provider = _CountingProvider(["alpha"])
    _ = embed_missing_chunks(db_path, provider, MODEL)

    result = embed_missing_chunks(db_path, provider, "other-model")

    assert result.embedded == 1
    assert _stored_vectors(db_path) == 2


def test_identical_text_in_two_documents_is_embedded_once(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    shared = "# Shared\n\nexactly the same words"
    _ = upsert_document(db_path, _doc("/a.md", "A", shared))
    _ = upsert_document(db_path, _doc("/b.md", "B", shared))
    provider = _CountingProvider(["same"])

    result = embed_missing_chunks(db_path, provider, MODEL)

    assert result.embedded == 1
    assert _stored_vectors(db_path) == 1


def test_embeddings_survive_a_reindex_of_unchanged_content(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    body = "# One\n\nalpha"
    _ = upsert_document(db_path, _doc("/a.md", "A", body))
    provider = _CountingProvider(["alpha"])
    _ = embed_missing_chunks(db_path, provider, MODEL)

    _ = upsert_document(db_path, _doc("/a.md", "A", body))

    assert embed_missing_chunks(db_path, provider, MODEL).embedded == 0


def test_orphan_vectors_are_pruned(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha"))
    provider = _CountingProvider(["alpha"])
    _ = embed_missing_chunks(db_path, provider, MODEL)

    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\ncompletely different"))
    pruned = prune_orphan_embeddings(db_path)

    assert pruned == 1
    assert _stored_vectors(db_path) == 0


def test_has_embeddings_is_false_before_any_run(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha"))

    assert has_embeddings(db_path, MODEL) is False


def test_has_embeddings_is_true_after_a_run(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha"))
    _ = embed_missing_chunks(db_path, _CountingProvider(["alpha"]), MODEL)

    assert has_embeddings(db_path, MODEL) is True
    assert has_embeddings(db_path, "unused-model") is False


def test_semantic_search_ranks_the_closest_document_first(tmp_path: Path) -> None:
    """A document that never uses the query word still wins on meaning."""
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(
        db_path,
        _doc("/lexical.md", "Lexical", "# Note\n\nrollback appears here once"),
    )
    semantic_id = upsert_document(
        db_path,
        _doc("/semantic.md", "Semantic", "# Note\n\nrevert deploy undo release"),
    )
    provider = _CountingProvider(["revert", "deploy", "undo", "release"])
    _ = embed_missing_chunks(db_path, provider, MODEL)

    run = make_semantic_search(db_path, "revert deploy", provider, MODEL)
    assert run is not None
    hits = run()

    assert hits[0][0] == int(semantic_id)


def test_semantic_search_omits_unrelated_documents(tmp_path: Path) -> None:
    """A cosine of zero is evidence of no relationship, not a weak match."""
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# Note\n\nrevert now"))
    _ = upsert_document(db_path, _doc("/b.md", "B", "# Note\n\nnothing in common"))
    provider = _CountingProvider(["revert"])
    _ = embed_missing_chunks(db_path, provider, MODEL)

    run = make_semantic_search(db_path, "revert", provider, MODEL)
    assert run is not None

    assert [document_id for document_id, _ in run()] == [1]


def test_semantic_search_is_absent_without_stored_vectors(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha"))

    provider = _CountingProvider(["alpha"])
    assert make_semantic_search(db_path, "alpha", provider, MODEL) is None


def test_a_failing_provider_degrades_to_no_semantic_search(tmp_path: Path) -> None:
    class _Broken:
        def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
            raise OSError(len(texts))

    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha"))
    _ = embed_missing_chunks(db_path, _CountingProvider(["alpha"]), MODEL)

    assert make_semantic_search(db_path, "alpha", _Broken(), MODEL) is None


def test_hybrid_search_fuses_lexical_and_semantic_order(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    for name in ("first", "second", "third"):
        _ = upsert_document(
            db_path,
            _doc(f"/{name}.md", name.title(), f"# {name}\n\nshared body {name}"),
        )
    provider = _CountingProvider(["third"])
    _ = embed_missing_chunks(db_path, provider, MODEL)
    run = make_semantic_search(db_path, "third", provider, MODEL)
    assert run is not None

    results = search(db_path, "shared", limit=3, semantic=run)

    assert results[0].title == "Third"
    assert len(results) == 3


def test_a_semantic_only_hit_joins_the_results(tmp_path: Path) -> None:
    """The lexical query matches nothing, so the vector side must carry it."""
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# Note\n\nshared body"))
    _ = upsert_document(db_path, _doc("/b.md", "B", "# Note\n\nrevert the release"))
    provider = _CountingProvider(["revert", "release"])
    _ = embed_missing_chunks(db_path, provider, MODEL)
    run = make_semantic_search(db_path, "revert", provider, MODEL)
    assert run is not None

    results = search(db_path, "shared", limit=5, semantic=run)

    assert [result.title for result in results] == ["A", "B"]
    assert results[1].snippet != ""


def test_tag_scoping_still_applies_to_semantic_hits(tmp_path: Path) -> None:
    """A tag filter must not be bypassed by the vector side of retrieval."""
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(
        db_path,
        ParsedDocument(
            path="/a.md", title="A", tags=("project:one",), body="# N\n\nshared body"
        ),
    )
    _ = upsert_document(
        db_path,
        ParsedDocument(
            path="/b.md", title="B", tags=("project:two",), body="# N\n\nrevert release"
        ),
    )
    provider = _CountingProvider(["revert", "release"])
    _ = embed_missing_chunks(db_path, provider, MODEL)
    run = make_semantic_search(db_path, "revert", provider, MODEL)
    assert run is not None

    results = search(db_path, "shared", limit=5, tags=("project:one",), semantic=run)

    assert [result.title for result in results] == ["A"]


def test_search_without_a_reranker_is_unchanged(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc("/a.md", "A", "# One\n\nalpha shared"))

    assert [r.title for r in search(db_path, "shared", limit=3)] == ["A"]


def test_embedding_a_wiki_with_no_chunks_is_a_no_op(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"

    result = embed_missing_chunks(db_path, _CountingProvider(["x"]), MODEL)

    assert result.embedded == 0
    assert result.reused == 0
