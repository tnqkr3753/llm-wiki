"""Tests for the 5 new LLM-Wiki enhancements."""

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.doctor import check_fts5_trigram_support, run_doctor
from llm_wiki.git_hook import install_git_hook
from llm_wiki.hook_stats import show_hook_stats
from llm_wiki.models import ParsedDocument
from llm_wiki.store import search, upsert_document

runner = CliRunner()


def test_doctor_command(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".llm-wiki").mkdir()
    (project_dir / ".llm-wiki" / "config.toml").write_text("docs_dir = 'docs'", encoding="utf-8")

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
