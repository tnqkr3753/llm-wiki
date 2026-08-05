"""Tests for the 5 new LLM-Wiki enhancements."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.git_hook import install_git_hook
from llm_wiki.models import ParsedDocument
from llm_wiki.store import search, upsert_document

runner = CliRunner()


def test_doctor_command(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".llm-wiki").mkdir()
    (project_dir / ".llm-wiki" / "config.toml").write_text(
        "docs_dir = 'docs'", encoding="utf-8"
    )

    result = runner.invoke(app, ["doctor", "-p", str(project_dir)])
    assert result.exit_code == 0
    assert "LLM Wiki System & Workspace Diagnostics" in result.output
    assert "Python Version:" in result.output


def test_hook_stats_command() -> None:
    result = runner.invoke(app, ["hook-stats"])
    assert result.exit_code == 0
    assert "LLM Wiki Hook Performance & Token Savings" in result.output


def test_git_hook_install(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    git_dir = project_dir / ".git"
    git_dir.mkdir()

    hook_file = install_git_hook(project_dir, force=True)
    assert hook_file.is_file()
    assert "llm-wiki reindex" in hook_file.read_text(encoding="utf-8")


def test_fts_trigram_and_korean_search(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"

    doc1 = ParsedDocument(
        path="docs/test1.md",
        title="데이터정합성 가이드라인",
        tags=("guide", "data"),
        body="이 문서는 데이터정합성 검증 절차에 대해 설명합니다.",
    )
    doc2 = ParsedDocument(
        path="docs/test2.md",
        title="PostgreSQL 내보내기",
        tags=("db", "exporter"),
        body="Postgres exporter 설정 가이드입니다.",
    )

    upsert_document(db_path, doc1)
    upsert_document(db_path, doc2)

    # Korean query search
    results_ko = search(db_path, "정합성", limit=5)
    assert len(results_ko) == 1
    assert "데이터정합성" in results_ko[0].title


def test_bm25_min_score_filtering(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"

    doc1 = ParsedDocument(
        path="docs/test1.md",
        title="Python Code Formatting",
        tags=("python",),
        body="Python code style and ruff formatting settings.",
    )
    upsert_document(db_path, doc1)

    # Search with min_score threshold
    results_high_thresh = search(db_path, "Python", limit=5, min_score=9999.0)
    assert len(results_high_thresh) == 0

    results_normal = search(db_path, "Python", limit=5, min_score=0.0)
    assert len(results_normal) == 1


def test_doctor_warns_on_legacy_implicit_isolated_config(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / ".llm-wiki").mkdir(parents=True)
    (project_dir / ".llm-wiki" / "config.toml").write_text(
        'docs_dir = "docs"\ndb_path = ".llm-wiki/wiki.db"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["doctor", "-p", str(project_dir)])

    assert result.exit_code == 0
    assert "legacy" in result.output.lower()


def test_doctor_warns_when_global_mode_agents_points_to_local_db(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "demo-project"
    (project_dir / ".llm-wiki").mkdir(parents=True)
    (project_dir / ".llm-wiki" / "config.toml").write_text(
        'mode = "global"\nproject_tag = "project:demo-project"\ndocs_dir = "docs"\n',
        encoding="utf-8",
    )
    local_db = project_dir / ".llm-wiki" / "wiki.db"
    (project_dir / "AGENTS.md").write_text(
        f"# LLM Wiki Instructions\n\nllm-wiki ask-context --db {local_db}\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "-p", str(project_dir)])

    assert result.exit_code == 0
    assert "stale" in result.output.lower()


def test_doctor_reports_rows_outside_global_docs_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm_wiki.markdown import parse_markdown_file
    from llm_wiki.store import upsert_document

    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    external = tmp_path / "external.md"
    external.write_text("# External\n\nBody.\n", encoding="utf-8")
    _ = upsert_document(home / "wiki.db", parse_markdown_file(external))
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = runner.invoke(app, ["doctor", "-p", str(project_dir)])

    assert result.exit_code == 0
    assert "outside" in result.output.lower()


def test_sync_hook_for_global_mode_runs_vault_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from llm_wiki.git_hook import install_sync_hook

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    project = tmp_path / "demo-project"
    (project / ".git").mkdir(parents=True)
    (project / ".llm-wiki").mkdir()
    (project / ".llm-wiki" / "config.toml").write_text(
        'mode = "global"\nproject_tag = "project:demo-project"\ndocs_dir = "docs"\n',
        encoding="utf-8",
    )

    scripts = install_sync_hook(project)

    merge_hook = (project / ".git" / "hooks" / "post-merge").read_text("utf-8")
    assert (project / ".git" / "hooks" / "post-checkout").is_file()
    assert len(scripts) == 2
    assert f"--source demo-project={project / 'docs'}" in merge_hook
    assert f"--home {home}" in merge_hook
    assert "--apply" in merge_hook
    assert "reindex" in merge_hook
    assert f"--db {home / 'wiki.db'}" in merge_hook


def test_sync_hook_for_isolated_mode_reindexes_local_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from llm_wiki.git_hook import install_sync_hook

    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    project = tmp_path / "private-client"
    (project / ".git").mkdir(parents=True)
    (project / ".llm-wiki").mkdir()
    (project / ".llm-wiki" / "config.toml").write_text(
        'mode = "isolated"\ndocs_dir = "docs"\ndb_path = ".llm-wiki/wiki.db"\n',
        encoding="utf-8",
    )

    _ = install_sync_hook(project)

    merge_hook = (project / ".git" / "hooks" / "post-merge").read_text("utf-8")
    assert "vault import" not in merge_hook
    assert f"--db {project / '.llm-wiki' / 'wiki.db'}" in merge_hook


def test_sync_hook_requires_git_repository(tmp_path: Path) -> None:
    from llm_wiki.errors import WikiError
    from llm_wiki.git_hook import install_sync_hook

    project = tmp_path / "no-git"
    project.mkdir()

    with pytest.raises(WikiError):
        _ = install_sync_hook(project)
