"""Tests for the markdown file watcher."""

import time
from pathlib import Path

import pytest

from llm_wiki import watcher
from llm_wiki.store import search


def _write_doc(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\n\n{body}\n", encoding="utf-8")


def test_scan_mtimes_skips_hidden_and_vendor_directories(tmp_path: Path) -> None:
    _write_doc(tmp_path / "docs" / "real.md", "Real", "alpha")
    _write_doc(tmp_path / ".venv" / "hidden.md", "Hidden", "alpha")
    _write_doc(tmp_path / "node_modules" / "dep.md", "Dep", "alpha")

    snapshot = watcher.scan_mtimes(tmp_path)

    assert set(snapshot) == {tmp_path / "docs" / "real.md"}


def test_describe_changes_reports_added_modified_and_deleted(tmp_path: Path) -> None:
    added = tmp_path / "added.md"
    kept = tmp_path / "kept.md"
    removed = tmp_path / "removed.md"

    lines = watcher.describe_changes(
        {kept: 1.0, removed: 1.0},
        {kept: 2.0, added: 1.0},
        tmp_path,
    )

    assert lines == (
        "[green]Added:[/green] added.md",
        "[yellow]Modified:[/yellow] kept.md",
        "[red]Deleted:[/red] removed.md",
    )


def test_describe_changes_is_empty_when_nothing_moved(tmp_path: Path) -> None:
    unchanged = {tmp_path / "a.md": 1.0}

    assert watcher.describe_changes(unchanged, dict(unchanged), tmp_path) == ()


def test_run_watcher_reindexes_after_a_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "alpha.md", "Alpha", "alpha body")
    db_path = tmp_path / "wiki.db"
    monkeypatch.setenv("LLM_WIKI_DB", str(db_path))

    sleep_calls = 0

    def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            _write_doc(project_dir / "docs" / "beta.md", "Beta", "beta body")
            return
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", fake_sleep)

    watcher.run_watcher(project_dir, interval=0.0)

    assert len(search(db_path, "beta", limit=5)) == 1


def test_run_watcher_stops_without_reindexing_when_idle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "alpha.md", "Alpha", "alpha body")
    db_path = tmp_path / "wiki.db"
    monkeypatch.setenv("LLM_WIKI_DB", str(db_path))

    def fake_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", fake_sleep)

    watcher.run_watcher(project_dir, interval=0.0)

    assert not db_path.exists()
