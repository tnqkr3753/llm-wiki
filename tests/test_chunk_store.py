"""Tests for chunk persistence and chunk-scoped search snippets."""

import sqlite3
from contextlib import closing
from pathlib import Path

from llm_wiki.models import ParsedDocument
from llm_wiki.store import (
    document_chunks,
    reindex_directory,
    search,
    upsert_document,
)

MANUAL = """Preamble line.

# Restarting

Run `systemctl restart indexer` and wait.

# Rotating credentials

Issue a new token from the vault console.
"""


def _doc(path: Path, body: str, title: str = "Runbook") -> ParsedDocument:
    return ParsedDocument(path=str(path), title=title, tags=("ops",), body=body)


def _chunk_rows(db_path: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute(
            "SELECT document_id, ordinal, heading FROM document_chunks ORDER BY id"
        ).fetchall()


def test_upserting_a_document_stores_its_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"

    document_id = upsert_document(db_path, _doc(tmp_path / "runbook.md", MANUAL))

    chunks = document_chunks(db_path, document_id)
    assert [chunk.heading for chunk in chunks] == [
        "",
        "Restarting",
        "Rotating credentials",
    ]


def test_reindexing_replaces_chunks_instead_of_accumulating(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    doc_path = tmp_path / "runbook.md"

    first_id = upsert_document(db_path, _doc(doc_path, MANUAL))
    second_id = upsert_document(db_path, _doc(doc_path, "# Only\n\nOne section now.\n"))

    assert first_id == second_id
    assert [heading for _, _, heading in _chunk_rows(db_path)] == ["Only"]


def test_deleting_a_document_deletes_its_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    root = tmp_path / "wiki"
    root.mkdir()
    doc_path = root / "runbook.md"
    doc_path.write_text(f"---\ntitle: Runbook\ntags: ops\n---\n\n{MANUAL}", "utf-8")

    _ = reindex_directory(db_path, root)
    doc_path.unlink()
    result = reindex_directory(db_path, root)

    assert result.removed == 1
    assert _chunk_rows(db_path) == []


def test_a_search_snippet_quotes_the_section_that_matched(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc(tmp_path / "runbook.md", MANUAL))

    results = search(db_path, "vault console", limit=1)

    assert len(results) == 1
    assert "Rotating credentials" in results[0].snippet
    assert "systemctl" not in results[0].snippet


def test_a_snippet_falls_back_when_a_document_has_no_stored_chunks(
    tmp_path: Path,
) -> None:
    """Documents indexed before chunking existed must still return a snippet."""
    db_path = tmp_path / "wiki.db"
    _ = upsert_document(db_path, _doc(tmp_path / "runbook.md", MANUAL))
    with closing(sqlite3.connect(db_path)) as connection:
        _ = connection.execute("DELETE FROM document_chunks")
        connection.commit()

    results = search(db_path, "vault console", limit=1)

    assert len(results) == 1
    assert results[0].snippet != ""


def test_chunks_of_an_unknown_document_are_empty(tmp_path: Path) -> None:
    from llm_wiki.models import DocumentId

    assert document_chunks(tmp_path / "wiki.db", DocumentId(999)) == ()
