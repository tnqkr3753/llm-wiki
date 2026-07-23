"""SQLite FTS-backed document store."""

import re
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from llm_wiki.errors import DocumentNotFoundError, SqlColumnTypeError
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import DocumentId, ParsedDocument, SearchResult, StoredDocument

type SqlValue = str | int | float | bytes | None
type SqlRow = Sequence[SqlValue]


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    tags TEXT NOT NULL,
    body TEXT NOT NULL
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
    with closing(sqlite3.connect(db_path)) as connection:
        existing = _fetch_one(
            connection,
            "SELECT id FROM documents WHERE path = ?",
            (document.path,),
        )
        tags_text = ", ".join(document.tags)
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO documents (path, title, tags, body)
                VALUES (?, ?, ?, ?)
                """,
                (document.path, document.title, tags_text, document.body),
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
        connection.commit()
        return document_id


def search(
    db_path: Path, query: str, limit: int, min_score: float = 0.0
) -> list[SearchResult]:
    """Search indexed documents with SQLite FTS5."""
    initialize(db_path)
    fts_query = _literal_fts_query(query)
    if fts_query == "":
        return []
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
            (fts_query, limit),
        )

    results = []
    for row in rows:
        bm25_score = float(row[5]) if len(row) > 5 and row[5] is not None else 0.0
        if bm25_score >= min_score:
            results.append(_result_from_row(row))
    return results


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


def reindex_directory(db_path: Path, root_path: Path) -> int:
    """Reindex all markdown files in root_path into db_path."""
    indexed = 0
    for file_path in root_path.rglob("*.md"):
        if any(part.startswith(".") or part in ("venv", "node_modules", "__pycache__") for part in file_path.parts):
            continue
        try:
            doc = parse_markdown_file(file_path)
            upsert_document(db_path, doc)
            indexed += 1
        except Exception:
            pass
    return indexed
