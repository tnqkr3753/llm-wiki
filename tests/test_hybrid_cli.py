"""End-to-end tests for the embed command and hybrid retrieval in the CLI."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Self
from urllib.request import Request

import pytest
from typer.testing import CliRunner

from llm_wiki.cli import app

runner = CliRunner()
REFUSED = "connection refused"

VOCABULARY = ("restart", "indexer", "token", "vault", "revert")

RUNBOOK = """---
title: Runbook
tags: ops
---

# Restarting the indexer

Restart the indexer service when it stalls.

# Rotating the vault token

Issue a new token from the vault console.
"""


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _FakeServer:
    """A bag-of-words embedding server, good enough to rank deterministically."""

    def __init__(self) -> None:
        self.requests = 0
        self.texts: list[str] = []

    def __call__(self, request: Request, timeout: float = 0.0) -> _FakeResponse:
        assert isinstance(request.data, bytes)
        body = json.loads(request.data.decode("utf-8"))
        texts: list[str] = body["input"]
        self.requests += 1
        self.texts.extend(texts)
        return _FakeResponse({"embeddings": [self._vector(text) for text in texts]})

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.lower()
        return [1.0 if word in lowered else 0.0 for word in VOCABULARY]


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> _FakeServer:
    fake = _FakeServer()
    monkeypatch.setattr("llm_wiki.embedding.urlopen", fake)
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "fake-model")
    monkeypatch.setenv("LLM_WIKI_EMBED_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("LLM_WIKI_HOME", "/nonexistent-llm-wiki-home")
    return fake


def _wiki(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "wiki"
    root.mkdir()
    (root / "runbook.md").write_text(RUNBOOK, encoding="utf-8")
    return root, tmp_path / "wiki.db"


def _vector_count(db_path: Path) -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        return int(
            connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
        )


def test_reindex_embeds_new_chunks(tmp_path: Path, server: _FakeServer) -> None:
    root, db_path = _wiki(tmp_path)

    result = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])

    assert result.exit_code == 0
    assert "embedded 2 reused 0" in result.output
    assert _vector_count(db_path) == 2


def test_a_second_reindex_embeds_nothing(tmp_path: Path, server: _FakeServer) -> None:
    root, db_path = _wiki(tmp_path)
    _ = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])
    server.texts.clear()

    result = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])

    assert "embedded 0 reused 2" in result.output
    assert server.texts == []


def test_editing_one_section_re_embeds_only_that_section(
    tmp_path: Path,
    server: _FakeServer,
) -> None:
    root, db_path = _wiki(tmp_path)
    _ = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])
    (root / "runbook.md").write_text(
        RUNBOOK.replace("Issue a new token", "Issue a fresh token"), encoding="utf-8"
    )
    server.texts.clear()

    result = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])

    assert "embedded 1 reused 1" in result.output
    assert len(server.texts) == 1
    assert "vault" in server.texts[0].lower()


def test_embed_command_backfills_an_existing_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wiki indexed before embedding was configured can be caught up."""
    root, db_path = _wiki(tmp_path)
    monkeypatch.setenv("LLM_WIKI_HOME", "/nonexistent-llm-wiki-home")
    _ = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])
    assert _vector_count(db_path) == 0

    fake = _FakeServer()
    monkeypatch.setattr("llm_wiki.embedding.urlopen", fake)
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "fake-model")
    monkeypatch.setenv("LLM_WIKI_EMBED_URL", "http://127.0.0.1:11434")
    result = runner.invoke(app, ["embed", "--db", str(db_path)])

    assert result.exit_code == 0
    assert _vector_count(db_path) == 2


def test_embed_reports_when_embedding_is_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_HOME", "/nonexistent-llm-wiki-home")
    for name in ("LLM_WIKI_EMBED_MODEL", "LLM_WIKI_EMBED_URL"):
        monkeypatch.delenv(name, raising=False)

    result = runner.invoke(app, ["embed", "--db", str(tmp_path / "wiki.db")])

    assert result.exit_code == 0
    assert "not configured" in result.output


def test_a_down_server_leaves_the_wiki_searchable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refused(request: Request, timeout: float = 0.0) -> _FakeResponse:
        raise OSError(REFUSED)

    root, db_path = _wiki(tmp_path)
    monkeypatch.setattr("llm_wiki.embedding.urlopen", _refused)
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "fake-model")
    monkeypatch.setenv("LLM_WIKI_EMBED_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("LLM_WIKI_HOME", "/nonexistent-llm-wiki-home")

    reindexed = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])
    searched = runner.invoke(app, ["search", "vault", "--db", str(db_path)])

    assert reindexed.exit_code == 0
    assert "embedding incomplete" in reindexed.output
    assert searched.exit_code == 0
    assert "Runbook" in searched.output


def test_search_finds_a_document_by_meaning_alone(
    tmp_path: Path,
    server: _FakeServer,
) -> None:
    """A query sharing no words with the body still retrieves it."""
    root, db_path = _wiki(tmp_path)
    (root / "release.md").write_text(
        "---\ntitle: Release\ntags: ops\n---\n\n# Undo a release\n\nrevert quickly.\n",
        encoding="utf-8",
    )
    _ = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])

    result = runner.invoke(
        app, ["search", "revert vault", "--db", str(db_path), "--limit", "2"]
    )

    assert result.exit_code == 0
    assert "Release" in result.output


def test_doctor_reports_the_vector_cache(tmp_path: Path, server: _FakeServer) -> None:
    root, db_path = _wiki(tmp_path)
    project = tmp_path / "project"
    (project / ".llm-wiki").mkdir(parents=True)
    _ = runner.invoke(app, ["reindex", "-p", str(root), "--db", str(db_path)])
    (project / ".llm-wiki" / "wiki.db").write_bytes(db_path.read_bytes())

    result = runner.invoke(app, ["doctor", "-p", str(project)])

    assert "hybrid search active" in result.output
