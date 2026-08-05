"""SQLite FTS-backed document store."""

import math
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from llm_wiki.config import PROJECT_SLUG_PATTERN, PROJECT_TAG_PREFIX
from llm_wiki.errors import (
    DocumentNotFoundError,
    ProjectScopeError,
    SqlColumnTypeError,
    WikiError,
)
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import (
    DocumentId,
    DocumentLink,
    DocumentUsage,
    ParsedDocument,
    ReindexFailure,
    ReindexResult,
    SearchResult,
    StoredDocument,
)

type SqlValue = str | int | float | bytes | None
type SqlRow = Sequence[SqlValue]

EXCLUDED_DIR_NAMES: Final = frozenset({"venv", "node_modules", "__pycache__"})
BM25_COLUMN_INDEX: Final = 5
CANDIDATE_MULTIPLIER: Final = 4
MIN_CANDIDATES: Final = 20


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    tags TEXT NOT NULL,
    body TEXT NOT NULL
);
"""

SCHEMA_USAGE = """
CREATE TABLE IF NOT EXISTS document_usage (
    document_id INTEGER PRIMARY KEY,
    retrieved_count INTEGER NOT NULL DEFAULT 0,
    last_retrieved_at TEXT
);
"""

SCHEMA_LINKS = """
CREATE TABLE IF NOT EXISTS document_links (
    source_id INTEGER NOT NULL,
    target TEXT NOT NULL,
    PRIMARY KEY (source_id, target)
);
"""

SCHEMA_FTS_TRIGRAM = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    body,
    tags,
    content='documents',
    content_rowid='id',
    tokenize='trigram'
);
"""

SCHEMA_FTS_UNICODE61 = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    body,
    tags,
    content='documents',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
"""


def initialize(db_path: Path) -> None:
    """Create the database schema if needed."""
    _ensure_parent(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        _ = connection.executescript(SCHEMA)
        _ = connection.executescript(SCHEMA_USAGE)
        _ = connection.executescript(SCHEMA_LINKS)

        # Ensure documents_fts exists with trigram (or fallback unicode61)
        tables = _fetch_all(
            connection,
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents_fts'",
            (),
        )
        if not tables:
            try:
                _ = connection.executescript(SCHEMA_FTS_TRIGRAM)
            except sqlite3.OperationalError:
                _ = connection.executescript(SCHEMA_FTS_UNICODE61)
        else:
            # Rebuild FTS index if table structure is present
            sql_text = str(tables[0][0]) if tables[0] and tables[0][0] else ""
            if "trigram" not in sql_text:
                try:
                    _ = connection.execute("DROP TABLE IF EXISTS documents_fts")
                    _ = connection.executescript(SCHEMA_FTS_TRIGRAM)
                    _ = connection.execute(
                        """
                        INSERT INTO documents_fts (rowid, title, body, tags)
                        SELECT id, title, body, tags FROM documents
                        """
                    )
                except sqlite3.OperationalError:
                    pass

        connection.commit()


def upsert_document(db_path: Path, document: ParsedDocument) -> DocumentId:
    """Insert or replace one parsed document in the full-text index."""
    initialize(db_path)
    stored_path = canonical_path(document.path)
    with closing(sqlite3.connect(db_path)) as connection:
        existing = _fetch_one(
            connection,
            "SELECT id FROM documents WHERE path = ?",
            (stored_path,),
        )
        tags_text = ", ".join(document.tags)
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO documents (path, title, tags, body)
                VALUES (?, ?, ?, ?)
                """,
                (stored_path, document.title, tags_text, document.body),
            )
            document_id = DocumentId(_last_insert_id(cursor))
        else:
            document_id = DocumentId(_row_int(existing, 0))
            _ = connection.execute(
                "DELETE FROM documents_fts WHERE rowid = ?",
                (int(document_id),),
            )
            _ = connection.execute(
                """
                UPDATE documents
                SET title = ?, tags = ?, body = ?
                WHERE id = ?
                """,
                (document.title, tags_text, document.body, int(document_id)),
            )

        _ = connection.execute(
            """
            INSERT INTO documents_fts (rowid, title, body, tags)
            VALUES (?, ?, ?, ?)
            """,
            (int(document_id), document.title, document.body, tags_text),
        )
        _replace_links(connection, document_id, document.links)
        connection.commit()
        return document_id


def _replace_links(
    connection: sqlite3.Connection,
    document_id: DocumentId,
    links: tuple[str, ...],
) -> None:
    """Swap one document's outgoing wikilink targets for its current set."""
    _ = connection.execute(
        "DELETE FROM document_links WHERE source_id = ?",
        (int(document_id),),
    )
    for target in links:
        _ = connection.execute(
            "INSERT OR IGNORE INTO document_links (source_id, target) VALUES (?, ?)",
            (int(document_id), target),
        )


def search(
    db_path: Path,
    query: str,
    limit: int,
    min_score: float = 0.0,
    usage_weight: float = 0.0,
    tags: Sequence[str] = (),
    project: str | None = None,
) -> list[SearchResult]:
    """Search indexed documents with SQLite FTS5.

    With a positive ``usage_weight``, documents that have actually been
    retrieved for grounding are promoted over equally relevant ones that
    never were. A weight of zero leaves BM25 order untouched.

    ``tags`` scopes the results to documents carrying *every* given tag (exact
    membership, not substring). This is how one shared wiki is partitioned —
    e.g. ``project:foo`` — without splitting the index into separate databases.

    ``project`` selects one project's slice of the shared wiki: rows tagged
    exactly ``project:<slug>`` plus global/common rows carrying no project
    tag at all. Rows tagged only for other projects are excluded. ``tags``
    still applies afterwards.
    """
    initialize(db_path)
    project_tag = None if project is None else normalize_project_scope(project)
    fts_query = _literal_fts_query(query)
    if fts_query == "":
        return []
    filtered = bool(tags) or project_tag is not None
    widen = usage_weight > 0 or filtered
    # Tag/project filters must see every FTS candidate (LIMIT -1): a match for
    # the selected scope may rank below many out-of-scope rows and would be
    # lost behind a truncated candidate window.
    if filtered:
        fetch_limit = -1
    elif widen:
        fetch_limit = max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
    else:
        fetch_limit = limit
    with closing(sqlite3.connect(db_path)) as connection:
        rows = _fetch_all(
            connection,
            """
            SELECT
                d.id,
                d.path,
                d.title,
                d.tags,
                snippet(documents_fts, 1, '', '', ' ... ', 18) AS snippet,
                -bm25(documents_fts) AS bm25_score
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY bm25_score DESC
            LIMIT ?
            """,
            (fts_query, fetch_limit),
        )

    ranked = [row for row in rows if _row_bm25_score(row) >= min_score]
    if project_tag is not None:
        ranked = _filter_by_project(ranked, project_tag)
    if tags:
        ranked = _filter_by_tags(ranked, tags)
    if usage_weight > 0:
        ranked = _rank_by_usage(db_path, ranked, usage_weight)
    ranked = _demote_drafts(ranked)
    return [_result_from_row(row) for row in ranked[:limit]]


DRAFT_TAG: Final = "draft"


def _demote_drafts(rows: list[SqlRow]) -> list[SqlRow]:
    """Stable-partition results so `draft`-tagged captures rank below others.

    Officially promoted documents (committed to a project repo and mirrored
    into the vault) carry no `draft` tag; personal captures do. When both
    match a query the reviewed document wins, but a draft-only match is
    still returned.
    """
    official = [row for row in rows if DRAFT_TAG not in _split_tags(_row_str(row, 3))]
    drafts = [row for row in rows if DRAFT_TAG in _split_tags(_row_str(row, 3))]
    return official + drafts


def normalize_project_scope(value: str) -> str:
    """Turn CLI input like ``foo`` or ``project:foo`` into a stored tag."""
    candidate = value.strip()
    slug = candidate.removeprefix(PROJECT_TAG_PREFIX)
    if PROJECT_SLUG_PATTERN.fullmatch(slug) is None:
        raise ProjectScopeError.invalid(value)
    return f"{PROJECT_TAG_PREFIX}{slug}"


def _filter_by_project(rows: list[SqlRow], project_tag: str) -> list[SqlRow]:
    """Keep rows for the selected project plus rows with no project tag."""
    kept: list[SqlRow] = []
    for row in rows:
        row_tags = set(_split_tags(_row_str(row, 3)))
        has_project_tag = any(tag.startswith(PROJECT_TAG_PREFIX) for tag in row_tags)
        if not has_project_tag or project_tag in row_tags:
            kept.append(row)
    return kept


def _filter_by_tags(rows: list[SqlRow], tags: Sequence[str]) -> list[SqlRow]:
    """Keep only rows whose tag set contains every requested tag."""
    wanted = {tag.strip() for tag in tags if tag.strip() != ""}
    if not wanted:
        return rows
    return [row for row in rows if wanted <= set(_split_tags(_row_str(row, 3)))]


def _rank_by_usage(
    db_path: Path,
    rows: list[SqlRow],
    usage_weight: float,
) -> list[SqlRow]:
    """Re-rank BM25 candidates by how often each was retrieved before."""
    counts = _retrieved_counts(db_path, [_row_int(row, 0) for row in rows])
    return sorted(
        rows,
        key=lambda row: (
            -(
                _row_bm25_score(row)
                * (1.0 + usage_weight * math.log1p(counts.get(_row_int(row, 0), 0)))
            )
        ),
    )


def _retrieved_counts(db_path: Path, document_ids: list[int]) -> dict[int, int]:
    if not document_ids:
        return {}
    placeholders = ", ".join("?" for _ in document_ids)
    with closing(sqlite3.connect(db_path)) as connection:
        rows = _fetch_all(
            connection,
            f"""
            SELECT document_id, retrieved_count
            FROM document_usage
            WHERE document_id IN ({placeholders})
            """,  # noqa: S608 - placeholders are generated, never user input
            tuple(document_ids),
        )
    return {_row_int(row, 0): _coerce_count(row[1]) for row in rows}


def _coerce_count(value: SqlValue) -> int:
    """Read a retrieved-count defensively: a corrupt or negative value is 0.

    The count is advisory ranking input, never a correctness invariant, so a
    row corrupted outside the CLI must degrade to neutral rather than crash
    ``usage`` or usage-weighted ``ask-context``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def record_retrieval(
    db_path: Path,
    document_ids: Sequence[DocumentId],
    now: datetime | None = None,
) -> None:
    """Count one grounding use for each retrieved document."""
    if not document_ids:
        return
    initialize(db_path)
    moment = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as connection:
        for document_id in document_ids:
            _ = connection.execute(
                """
                INSERT INTO document_usage (
                    document_id, retrieved_count, last_retrieved_at
                )
                VALUES (?, 1, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    retrieved_count = retrieved_count + 1,
                    last_retrieved_at = excluded.last_retrieved_at
                """,
                (int(document_id), moment),
            )
        connection.commit()


def usage_report(db_path: Path) -> tuple[DocumentUsage, ...]:
    """List every indexed document, most retrieved first."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        rows = _fetch_all(
            connection,
            """
            SELECT
                d.id,
                d.path,
                d.title,
                COALESCE(u.retrieved_count, 0) AS retrieved_count,
                u.last_retrieved_at
            FROM documents d
            LEFT JOIN document_usage u ON u.document_id = d.id
            ORDER BY retrieved_count DESC, d.id ASC
            """,
            (),
        )
    return tuple(_usage_from_row(row) for row in rows)


def _usage_from_row(row: SqlRow) -> DocumentUsage:
    last_retrieved = row[4]
    return DocumentUsage(
        id=DocumentId(_row_int(row, 0)),
        path=_row_str(row, 1),
        title=_row_str(row, 2),
        retrieved_count=_coerce_count(row[3]),
        last_retrieved_at=last_retrieved if isinstance(last_retrieved, str) else None,
    )


def _row_bm25_score(row: SqlRow) -> float:
    """Read the BM25 score column, treating a missing score as neutral."""
    if len(row) <= BM25_COLUMN_INDEX:
        return 0.0
    value = row[BM25_COLUMN_INDEX]
    if not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def get_document(db_path: Path, document_id: DocumentId) -> StoredDocument:
    """Load one stored document by id."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        row = _fetch_one(
            connection,
            "SELECT id, path, title, tags, body FROM documents WHERE id = ?",
            (int(document_id),),
        )
    if row is None:
        raise DocumentNotFoundError.for_id(int(document_id))
    return _document_from_row(row)


def _ensure_parent(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _last_insert_id(cursor: sqlite3.Cursor) -> int:
    lastrowid = cursor.lastrowid
    if lastrowid is None:
        raise SqlColumnTypeError.expected_integer(0)
    return lastrowid


def _fetch_one(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[SqlValue, ...],
) -> SqlRow | None:
    row = connection.execute(sql, parameters).fetchone()
    if row is None:
        return None
    return tuple(_normalize_sql_value(value) for value in row)


def _fetch_all(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[SqlValue, ...],
) -> list[SqlRow]:
    rows = connection.execute(sql, parameters).fetchall()
    return [tuple(_normalize_sql_value(value) for value in row) for row in rows]


def _normalize_sql_value(value: SqlValue) -> SqlValue:
    return value


def _literal_fts_query(query: str) -> str:
    tokens = re.findall(
        r"[\w\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]+",
        query,
    )
    if not tokens:
        return ""
    return " ".join(f'"{token}"' for token in tokens)


def _row_int(row: SqlRow, index: int) -> int:
    value = row[index]
    if not isinstance(value, int):
        raise SqlColumnTypeError.expected_integer(index)
    return value


def _row_str(row: SqlRow, index: int) -> str:
    value = row[index]
    if not isinstance(value, str):
        raise SqlColumnTypeError.expected_text(index)
    return value


def _split_tags(tags_text: str) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in tags_text.split(",") if tag.strip() != "")


def _result_from_row(row: SqlRow) -> SearchResult:
    return SearchResult(
        id=DocumentId(_row_int(row, 0)),
        path=_row_str(row, 1),
        title=_row_str(row, 2),
        tags=_split_tags(_row_str(row, 3)),
        snippet=_row_str(row, 4),
    )


def _document_from_row(row: SqlRow) -> StoredDocument:
    return StoredDocument(
        id=DocumentId(_row_int(row, 0)),
        path=_row_str(row, 1),
        title=_row_str(row, 2),
        tags=_split_tags(_row_str(row, 3)),
        body=_row_str(row, 4),
    )


def outgoing_links(db_path: Path, document_id: DocumentId) -> tuple[DocumentLink, ...]:
    """List indexed documents this document links to, in first-seen order."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        targets = [
            _row_str(row, 0)
            for row in _fetch_all(
                connection,
                "SELECT target FROM document_links WHERE source_id = ? ORDER BY rowid",
                (int(document_id),),
            )
        ]
        documents = _document_index(connection)

    resolved: list[DocumentLink] = []
    seen: set[int] = {int(document_id)}
    for target in targets:
        match = _resolve_target(target, documents)
        if match is not None and int(match.id) not in seen:
            seen.add(int(match.id))
            resolved.append(match)
    return tuple(resolved)


def backlinks(db_path: Path, document_id: DocumentId) -> tuple[DocumentLink, ...]:
    """List indexed documents that link to this document, in document order."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        documents = _document_index(connection)
        edges = _fetch_all(
            connection,
            "SELECT source_id, target FROM document_links ORDER BY source_id, rowid",
            (),
        )

    by_id = {int(link.id): link for link in documents}
    incoming: list[DocumentLink] = []
    seen: set[int] = set()
    for edge in edges:
        source_id = _row_int(edge, 0)
        if source_id == int(document_id) or source_id in seen:
            continue
        match = _resolve_target(_row_str(edge, 1), documents)
        if match is not None and int(match.id) == int(document_id):
            source = by_id.get(source_id)
            if source is not None:
                seen.add(source_id)
                incoming.append(source)
    return tuple(incoming)


def link_graph(
    db_path: Path,
) -> tuple[
    tuple[DocumentLink, ...],
    tuple[tuple[int, int], ...],
    tuple[str, ...],
]:
    """Return all documents, resolved link edges, and unresolved link targets."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        documents = _document_index(connection)
        edges = _fetch_all(
            connection,
            "SELECT source_id, target FROM document_links ORDER BY source_id, rowid",
            (),
        )

    resolved: list[tuple[int, int]] = []
    unresolved: list[str] = []
    for edge in edges:
        source_id = _row_int(edge, 0)
        target = _row_str(edge, 1)
        match = _resolve_target(target, documents)
        if match is None:
            if target not in unresolved:
                unresolved.append(target)
        elif int(match.id) != source_id:
            resolved.append((source_id, int(match.id)))
    return tuple(documents), tuple(resolved), tuple(unresolved)


def _document_index(connection: sqlite3.Connection) -> list[DocumentLink]:
    rows = _fetch_all(connection, "SELECT id, path, title FROM documents", ())
    return [
        DocumentLink(
            id=DocumentId(_row_int(row, 0)),
            path=_row_str(row, 1),
            title=_row_str(row, 2),
        )
        for row in rows
    ]


def _resolve_target(
    target: str,
    documents: list[DocumentLink],
) -> DocumentLink | None:
    """Resolve a wikilink target to a document by relative path or basename."""
    wanted = _normalize_link_path(target)
    if wanted == "":
        return None
    wanted_stem = wanted.rsplit("/", 1)[-1]
    for document in documents:
        doc_path = _normalize_link_path(document.path)
        if doc_path == wanted or doc_path.endswith("/" + wanted):
            return document
    for document in documents:
        if _normalize_link_path(document.path).rsplit("/", 1)[-1] == wanted_stem:
            return document
    return None


def _normalize_link_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip().removesuffix(".md")
    return normalized.removeprefix("./")


def reindex_directory(db_path: Path, root_path: Path) -> ReindexResult:
    """Reindex every Markdown file under root_path and drop deleted ones."""
    root = root_path.expanduser().resolve()
    indexed = 0
    failures: list[ReindexFailure] = []
    for file_path in iter_markdown_files(root):
        try:
            document = parse_markdown_file(file_path)
        except WikiError as exc:
            failures.append(ReindexFailure(path=str(file_path), reason=str(exc)))
            continue
        _ = upsert_document(db_path, document)
        indexed += 1

    removed = _remove_missing_documents(db_path, root)
    return ReindexResult(indexed=indexed, removed=removed, failures=tuple(failures))


def canonical_path(path: str) -> str:
    """Resolve a document path to a stable absolute form for the index.

    Storing the canonical path keeps one file from being indexed twice under
    different spellings (relative vs absolute, `..` segments, `/tmp` symlinked
    to `/private/tmp`), which would otherwise create duplicate rows.
    """
    return str(Path(path).expanduser().resolve())


def iter_markdown_files(root_path: Path) -> Iterator[Path]:
    """Yield every indexable Markdown file under root_path in stable order."""
    root = root_path.expanduser().resolve()
    for file_path in sorted(root.rglob("*.md")):
        if _is_excluded(file_path, root):
            continue
        # A symlink (or `..`) can name a file that escapes the root; indexing it
        # would pull external content into this wiki. Only crawl files that
        # actually live under the root once resolved.
        if not file_path.resolve().is_relative_to(root):
            continue
        yield file_path


def _is_excluded(file_path: Path, root: Path) -> bool:
    """Report whether a file sits in a hidden or vendored directory."""
    relative_parts = file_path.relative_to(root).parts
    return any(
        part.startswith(".") or part in EXCLUDED_DIR_NAMES for part in relative_parts
    )


def _remove_missing_documents(db_path: Path, root: Path) -> int:
    """Delete indexed documents under root whose source file no longer exists."""
    initialize(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        rows = _fetch_all(connection, "SELECT id, path FROM documents", ())
        stale_ids = [
            _row_int(row, 0)
            for row in rows
            if _is_stale_document(_row_str(row, 1), root)
        ]
        for document_id in stale_ids:
            # Delete from the FTS index first: the external content row must
            # still hold the old values for FTS5 to unindex them correctly.
            _ = connection.execute(
                "DELETE FROM documents_fts WHERE rowid = ?",
                (document_id,),
            )
            _ = connection.execute(
                "DELETE FROM documents WHERE id = ?",
                (document_id,),
            )
            _ = connection.execute(
                "DELETE FROM document_usage WHERE document_id = ?",
                (document_id,),
            )
            _ = connection.execute(
                "DELETE FROM document_links WHERE source_id = ?",
                (document_id,),
            )
        # Prune any usage row whose document is gone, however it was orphaned,
        # so stale counts cannot accumulate or skew usage-weighted ranking.
        _ = connection.execute(
            "DELETE FROM document_usage WHERE document_id NOT IN "
            "(SELECT id FROM documents)"
        )
        connection.commit()
    return len(stale_ids)


def _is_stale_document(stored_path: str, root: Path) -> bool:
    """Report whether a stored path belongs to root but is gone from disk.

    Relative stored paths are never treated as stale: they were indexed
    against an unknown working directory, so their absence cannot be proven.
    The path is resolved before the root check so a `..` segment cannot make a
    document that lives outside the root look like it belongs to it — which
    would let reindexing one root delete another root's documents.
    """
    path = Path(stored_path)
    if not path.is_absolute():
        return False
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        return False
    return not resolved.is_file()
