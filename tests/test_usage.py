"""Tests for retrieval usage tracking and usage-weighted ranking."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.models import DocumentId, ParsedDocument
from llm_wiki.store import (
    record_retrieval,
    reindex_directory,
    search,
    upsert_document,
    usage_report,
)

runner = CliRunner()


def _index(db_path: Path, path: str, title: str, body: str) -> DocumentId:
    return upsert_document(
        db_path,
        ParsedDocument(path=path, title=title, tags=("test",), body=body),
    )


def test_usage_starts_at_zero_for_a_newly_indexed_document(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = _index(db_path, "/docs/a.md", "Alpha", "shared body")

    report = usage_report(db_path)

    assert [(item.title, item.retrieved_count) for item in report] == [("Alpha", 0)]
    assert report[0].last_retrieved_at is None


def test_record_retrieval_counts_each_grounding(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    document_id = _index(db_path, "/docs/a.md", "Alpha", "shared body")
    moment = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)

    record_retrieval(db_path, [document_id], now=moment)
    record_retrieval(db_path, [document_id], now=moment)

    report = usage_report(db_path)
    assert report[0].retrieved_count == 2
    assert report[0].last_retrieved_at == moment.isoformat(timespec="seconds")


def test_usage_report_ranks_most_retrieved_first(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    quiet = _index(db_path, "/docs/quiet.md", "Quiet", "shared body")
    busy = _index(db_path, "/docs/busy.md", "Busy", "shared body")
    record_retrieval(db_path, [busy, busy])

    titles = [item.title for item in usage_report(db_path)]

    assert titles == ["Busy", "Quiet"]
    assert quiet != busy


def test_search_does_not_record_retrievals(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = _index(db_path, "/docs/a.md", "Alpha", "shared body")

    _ = search(db_path, "shared", limit=5)

    assert usage_report(db_path)[0].retrieved_count == 0


def test_usage_weight_promotes_a_previously_retrieved_document(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wiki.db"
    first = _index(db_path, "/docs/first.md", "First", "identical body text")
    second = _index(db_path, "/docs/second.md", "Second", "identical body text")
    baseline = [result.id for result in search(db_path, "identical", limit=2)]
    record_retrieval(db_path, [second, second, second])

    boosted = [
        result.id for result in search(db_path, "identical", limit=2, usage_weight=0.5)
    ]

    assert baseline[0] == first
    assert boosted[0] == second


def test_default_search_ignores_usage(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    first = _index(db_path, "/docs/first.md", "First", "identical body text")
    second = _index(db_path, "/docs/second.md", "Second", "identical body text")
    record_retrieval(db_path, [second, second, second])
    assert first != second

    results = [result.id for result in search(db_path, "identical", limit=2)]

    assert results[0] == first


def test_reindex_drops_usage_rows_for_deleted_documents(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    doc_path = project_dir / "docs" / "gone.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text("---\ntitle: Gone\n---\n\nbody\n", encoding="utf-8")
    result = reindex_directory(db_path, project_dir)
    assert result.indexed == 1
    record_retrieval(db_path, [item.id for item in usage_report(db_path)])

    doc_path.unlink()
    _ = reindex_directory(db_path, project_dir)

    assert usage_report(db_path) == ()


def test_ask_context_records_what_it_grounded(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _ = _index(db_path, "/docs/a.md", "Alpha", "grounded knowledge")
    _ = _index(db_path, "/docs/b.md", "Beta", "unrelated matter")

    result = runner.invoke(
        app, ["ask-context", "grounded", "--db", str(db_path), "--limit", "1"]
    )

    assert result.exit_code == 0
    counts = {item.title: item.retrieved_count for item in usage_report(db_path)}
    assert counts == {"Alpha": 1, "Beta": 0}


def test_usage_command_lists_never_retrieved_documents(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    used = _index(db_path, "/docs/used.md", "Used", "shared body")
    _ = _index(db_path, "/docs/unused.md", "Unused", "shared body")
    record_retrieval(db_path, [used])

    result = runner.invoke(app, ["usage", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Used" in result.output
    assert "Unused" in result.output
    assert "never retrieved: 1" in result.output


def test_usage_report_survives_a_corrupted_retrieved_count(tmp_path: Path) -> None:
    """A non-integer count must be reported as 0, not crash the command."""
    db_path = tmp_path / "wiki.db"
    document_id = _index(db_path, "/docs/a.md", "Alpha", "shared body")
    with closing(sqlite3.connect(db_path)) as conn:
        _ = conn.execute(
            "INSERT INTO document_usage "
            "(document_id, retrieved_count, last_retrieved_at) VALUES (?, ?, NULL)",
            (int(document_id), "corrupt"),
        )
        conn.commit()

    report = usage_report(db_path)

    assert report[0].retrieved_count == 0


def test_ask_context_survives_a_corrupted_retrieved_count(tmp_path: Path) -> None:
    """Usage-weighted ranking must not crash on a corrupted count."""
    db_path = tmp_path / "wiki.db"
    document_id = _index(db_path, "/docs/a.md", "Alpha", "grounded knowledge")
    with closing(sqlite3.connect(db_path)) as conn:
        _ = conn.execute(
            "INSERT INTO document_usage "
            "(document_id, retrieved_count, last_retrieved_at) VALUES (?, ?, NULL)",
            (int(document_id), "corrupt"),
        )
        conn.commit()

    result = runner.invoke(
        app, ["ask-context", "grounded", "--db", str(db_path), "--usage-weight", "0.5"]
    )

    assert result.exit_code == 0
    assert "Alpha" in result.output


def test_reindex_prunes_orphan_usage_rows(tmp_path: Path) -> None:
    """Usage rows with no surviving document must be cleaned up on reindex."""
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    doc = project_dir / "docs" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\ntitle: Alpha\n---\n\nbody\n", encoding="utf-8")
    _ = reindex_directory(db_path, project_dir)
    with closing(sqlite3.connect(db_path)) as conn:
        _ = conn.execute(
            "INSERT INTO document_usage (document_id, retrieved_count) VALUES (9999, 5)"
        )
        conn.commit()

    _ = reindex_directory(db_path, project_dir)

    with closing(sqlite3.connect(db_path)) as conn:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM document_usage WHERE document_id = 9999"
        ).fetchone()[0]
    assert orphans == 0
