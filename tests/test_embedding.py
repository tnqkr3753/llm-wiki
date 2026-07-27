"""Tests for embedding settings resolution and the provider contract."""

from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.embedding import (
    EmbeddingProvider,
    EmbeddingSettings,
    load_provider,
    resolve_embedding_settings,
)
from llm_wiki.models import ParsedDocument
from llm_wiki.store import search, upsert_document

runner = CliRunner()

EMBED_ENV_VARS = (
    "LLM_WIKI_EMBED_MODEL",
    "LLM_WIKI_EMBED_URL",
    "LLM_WIKI_EMBED_DIM",
    "LLM_WIKI_EMBED_ALLOW_REMOTE",
)


@pytest.fixture(autouse=True)
def _clear_embed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in EMBED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_WIKI_HOME", "/nonexistent-llm-wiki-home")


def _write_project_config(project_dir: Path, body: str) -> None:
    config_dir = project_dir / ".llm-wiki"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(body, encoding="utf-8")


def test_embedding_is_unconfigured_by_default(tmp_path: Path) -> None:
    assert resolve_embedding_settings(start_path=tmp_path) is None


def test_a_local_model_path_is_enough_to_configure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "/models/bge-small-ko")

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.model == "/models/bge-small-ko"
    assert settings.endpoint is None
    assert settings.is_blocked is False


def test_project_config_supplies_embedding_settings(tmp_path: Path) -> None:
    _write_project_config(
        tmp_path,
        "[embedding]\nmodel = 'bge-m3'\nendpoint = 'http://127.0.0.1:11434'\n"
        "dimension = 1024\n",
    )

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings == EmbeddingSettings(
        model="bge-m3",
        endpoint="http://127.0.0.1:11434",
        dimension=1024,
        allow_remote=False,
    )


def test_environment_overrides_project_config_per_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project_config(
        tmp_path,
        "[embedding]\nmodel = 'bge-m3'\nendpoint = 'http://127.0.0.1:11434'\n",
    )
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "bge-small")

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.model == "bge-small"
    assert settings.endpoint == "http://127.0.0.1:11434"


def test_a_loopback_endpoint_is_not_remote(tmp_path: Path) -> None:
    _write_project_config(
        tmp_path,
        "[embedding]\nmodel = 'bge-m3'\nendpoint = 'http://localhost:8080/embed'\n",
    )

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.is_remote is False
    assert settings.is_blocked is False


def test_a_remote_endpoint_is_blocked_unless_explicitly_allowed(
    tmp_path: Path,
) -> None:
    _write_project_config(
        tmp_path,
        "[embedding]\nmodel = 'text-embedding-3-small'\n"
        "endpoint = 'https://api.example.com/v1/embeddings'\n",
    )

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.is_remote is True
    assert settings.is_blocked is True


def test_a_remote_endpoint_can_be_opted_into(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project_config(
        tmp_path,
        "[embedding]\nmodel = 'text-embedding-3-small'\n"
        "endpoint = 'https://api.example.com/v1/embeddings'\n",
    )
    monkeypatch.setenv("LLM_WIKI_EMBED_ALLOW_REMOTE", "1")

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.is_blocked is False


def test_a_non_numeric_dimension_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "bge-small")
    monkeypatch.setenv("LLM_WIKI_EMBED_DIM", "not-a-number")

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.dimension is None


def test_no_backend_is_installed_yet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "bge-small")
    settings = resolve_embedding_settings(start_path=tmp_path)
    assert settings is not None

    assert load_provider(settings) is None


def test_a_provider_only_needs_to_embed_texts() -> None:
    class StubProvider:
        def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
            return tuple((float(len(text)),) for text in texts)

    provider: EmbeddingProvider = StubProvider()

    assert provider.embed(["ab", "abc"]) == ((2.0,), (3.0,))


def test_configuring_embedding_does_not_change_search_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "wiki.db"
    for name in ("alpha", "beta"):
        _ = upsert_document(
            db_path,
            ParsedDocument(
                path=f"/docs/{name}.md",
                title=name.title(),
                tags=(),
                body=f"{name} shared body",
            ),
        )
    before = [result.id for result in search(db_path, "shared", limit=5)]

    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "bge-small")
    monkeypatch.setenv("LLM_WIKI_EMBED_URL", "http://127.0.0.1:11434")

    after = [result.id for result in search(db_path, "shared", limit=5)]

    assert after == before


def test_doctor_reports_embedding_as_not_configured(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = runner.invoke(app, ["doctor", "-p", str(project_dir)])

    assert result.exit_code == 0
    assert "Embedding" in result.output
    assert "Not configured" in result.output


def test_doctor_warns_about_a_blocked_remote_endpoint(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _write_project_config(
        project_dir,
        "[embedding]\nmodel = 'text-embedding-3-small'\n"
        "endpoint = 'https://api.example.com/v1/embeddings'\n",
    )

    result = runner.invoke(app, ["doctor", "-p", str(project_dir)])

    assert result.exit_code == 0
    assert "remote endpoint blocked" in result.output


def test_global_config_supplies_fields_absent_from_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-field resolution: project supplies endpoint, global supplies model."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[embedding]\nmodel = 'global-model'\n", encoding="utf-8"
    )
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))
    project = tmp_path / "project"
    _write_project_config(project, "[embedding]\nendpoint = 'http://127.0.0.1:11434'\n")

    settings = resolve_embedding_settings(start_path=project)

    assert settings is not None
    assert settings.model == "global-model"
    assert settings.endpoint == "http://127.0.0.1:11434"


def test_project_config_overrides_global_per_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        "[embedding]\nmodel = 'global-model'\ndimension = 256\n", encoding="utf-8"
    )
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))
    project = tmp_path / "project"
    _write_project_config(project, "[embedding]\nmodel = 'project-model'\n")

    settings = resolve_embedding_settings(start_path=project)

    assert settings is not None
    assert settings.model == "project-model"
    assert settings.dimension == 256


def test_doctor_does_not_leak_endpoint_credentials(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project_config(
        project,
        "[embedding]\nmodel = 'bge-m3'\n"
        "endpoint = 'https://user:s3cr3t@api.example.com/embed?token=abc'\n"
        "allow_remote = true\n",
    )

    result = runner.invoke(app, ["doctor", "-p", str(project)])

    assert result.exit_code == 0
    assert "s3cr3t" not in result.output
    assert "token=abc" not in result.output
    assert "api.example.com" in result.output


def test_doctor_survives_a_malformed_project_config(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_dir = project / ".llm-wiki"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        "this is = not = valid toml\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["doctor", "-p", str(project)])

    assert result.exit_code == 0
    assert "Embedding" in result.output
