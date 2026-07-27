"""Tests for directory reindexing and the `reindex` command."""

import re
from pathlib import Path

from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.git_hook import install_git_hook
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import ParsedDocument
from llm_wiki.store import reindex_directory, search, upsert_document

runner = CliRunner()


def _write_doc(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\ntags: test\n---\n\n{body}\n",
        encoding="utf-8",
    )


def _registered_command_names() -> set[str]:
    return {
        info.name or ""
        for info in app.registered_commands
        if info.name is not None or info.callback is not None
    }


def test_git_hook_only_references_registered_commands(tmp_path: Path) -> None:
    """The installed post-commit hook must not call a nonexistent command."""
    project_dir = tmp_path / "project"
    (project_dir / ".git").mkdir(parents=True)

    hook_file = install_git_hook(project_dir)
    called = set(re.findall(r"llm-wiki ([a-z][a-z-]*)", hook_file.read_text("utf-8")))

    assert called
    assert called <= _registered_command_names()


def test_reindex_command_indexes_markdown_files(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "alpha.md", "Alpha", "alpha content")
    _write_doc(project_dir / "docs" / "beta.md", "Beta", "beta content")

    result = runner.invoke(
        app, ["reindex", "-p", str(project_dir), "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "2" in result.output
    assert len(search(db_path, "content", limit=10)) == 2


def test_reindex_removes_documents_for_deleted_files(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    keep = project_dir / "docs" / "keep.md"
    drop = project_dir / "docs" / "drop.md"
    _write_doc(keep, "Keep", "durable content")
    _write_doc(drop, "Drop", "durable content")
    _ = reindex_directory(db_path, project_dir)

    drop.unlink()
    result = reindex_directory(db_path, project_dir)

    assert result.indexed == 1
    assert result.removed == 1
    paths = [item.path for item in search(db_path, "durable", limit=10)]
    assert paths == [str(keep.resolve())]


def test_reindex_keeps_documents_indexed_from_other_roots(tmp_path: Path) -> None:
    """Reindexing one project must never evict another root's documents."""
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    other_dir = tmp_path / "global"
    _write_doc(project_dir / "docs" / "local.md", "Local", "shared content")
    _write_doc(other_dir / "docs" / "global.md", "Global", "shared content")
    _ = reindex_directory(db_path, project_dir)
    _ = reindex_directory(db_path, other_dir)

    result = reindex_directory(db_path, project_dir)

    assert result.removed == 0
    assert len(search(db_path, "shared", limit=10)) == 2


def test_reindex_reports_unreadable_files_instead_of_silently_skipping(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "good.md", "Good", "good content")
    broken = project_dir / "docs" / "broken.md"
    broken.write_bytes(b"---\ntitle: Broken\n---\n\n\xff\xfe invalid utf-8\n")

    result = reindex_directory(db_path, project_dir)

    assert result.indexed == 1
    assert [failure.path for failure in result.failures] == [str(broken.resolve())]
    assert result.failures[0].reason


def test_reindex_command_reports_failures_on_stderr_and_exits_nonzero(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "good.md", "Good", "good content")
    (project_dir / "docs" / "broken.md").write_bytes(b"\xff\xfe not utf-8")

    result = runner.invoke(
        app, ["reindex", "-p", str(project_dir), "--db", str(db_path)]
    )

    assert result.exit_code == 1
    assert "broken.md" in result.output


def test_reindex_skips_hidden_and_vendor_directories(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "real.md", "Real", "vendor content")
    _write_doc(project_dir / ".venv" / "hidden.md", "Hidden", "vendor content")
    _write_doc(project_dir / "node_modules" / "dep.md", "Dep", "vendor content")

    result = reindex_directory(db_path, project_dir)

    assert result.indexed == 1
    assert len(search(db_path, "vendor", limit=10)) == 1


def test_reindex_ignores_markdown_symlinks_pointing_outside_root(
    tmp_path: Path,
) -> None:
    """A .md symlink to an external file must not leak its content into the DB."""
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "real.md", "Real", "inside content")
    secret = tmp_path / "secret.md"
    secret.write_text(
        "---\ntitle: Secret\n---\n\nexternal secret content\n", encoding="utf-8"
    )
    (project_dir / "docs" / "link.md").symlink_to(secret)

    result = reindex_directory(db_path, project_dir)

    assert result.indexed == 1
    assert search(db_path, "secret", limit=10) == []


def test_reindex_does_not_delete_documents_that_resolve_outside_root(
    tmp_path: Path,
) -> None:
    """Reindexing one root must never evict a document that resolves elsewhere."""
    db_path = tmp_path / "wiki.db"
    project_dir = tmp_path / "project"
    _write_doc(project_dir / "docs" / "keep.md", "Keep", "project content")
    _ = reindex_directory(db_path, project_dir)

    # Lexically under project_dir, but `..` resolves it outside the root.
    lexical = project_dir / "docs" / ".." / ".." / "outside" / "ghost.md"
    _ = upsert_document(
        db_path,
        ParsedDocument(path=str(lexical), title="Ghost", tags=(), body="ghost content"),
    )

    result = reindex_directory(db_path, project_dir)

    assert result.removed == 0
    assert [item.title for item in search(db_path, "ghost", limit=10)] == ["Ghost"]


def test_indexing_the_same_file_by_different_paths_does_not_duplicate(
    tmp_path: Path,
) -> None:
    """A canonical and a non-canonical spelling must map to one indexed row."""
    db_path = tmp_path / "wiki.db"
    doc = tmp_path / "docs" / "alpha.md"
    _write_doc(doc, "Alpha", "canonical content")

    _ = upsert_document(db_path, parse_markdown_file(doc))
    non_canonical = doc.parent / ".." / "docs" / "alpha.md"
    _ = upsert_document(db_path, parse_markdown_file(non_canonical))

    assert len(search(db_path, "canonical", limit=10)) == 1
