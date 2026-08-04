"""Tests for database path resolution precedence."""

from pathlib import Path

import pytest

from llm_wiki.config import (
    find_project_config,
    resolve_db_path,
    resolve_home_path,
    resolve_project_config,
    resolve_project_tag,
)
from llm_wiki.errors import ConfigReadError


def _write_project_config(project_dir: Path, body: str) -> Path:
    config_dir = project_dir / ".llm-wiki"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_explicit_db_wins_over_every_other_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_DB", str(tmp_path / "env.db"))
    _write_project_config(tmp_path, f"db_path = '{tmp_path / 'project.db'}'")

    assert resolve_db_path(tmp_path / "explicit.db") == tmp_path / "explicit.db"


def test_environment_db_wins_over_project_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_DB", str(tmp_path / "env.db"))
    _write_project_config(tmp_path, f"db_path = '{tmp_path / 'project.db'}'")

    assert resolve_db_path(None, start_path=tmp_path) == tmp_path / "env.db"


def test_project_config_resolves_relative_paths_against_the_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    _write_project_config(tmp_path, "db_path = '.llm-wiki/wiki.db'")

    resolved = resolve_db_path(None, start_path=tmp_path)

    assert resolved == tmp_path / ".llm-wiki" / "wiki.db"


def test_falls_back_to_the_global_home_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("LLM_WIKI_HOME", str(home_dir))
    empty_project = tmp_path / "empty"
    empty_project.mkdir()

    assert resolve_db_path(None, start_path=empty_project) == home_dir / "wiki.db"


def test_global_config_db_path_overrides_the_default_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    (home_dir / "config.toml").write_text("db_path = 'shared.db'", encoding="utf-8")
    monkeypatch.setenv("LLM_WIKI_HOME", str(home_dir))
    empty_project = tmp_path / "empty"
    empty_project.mkdir()

    assert resolve_db_path(None, start_path=empty_project) == home_dir / "shared.db"


def test_finds_the_nearest_project_config_from_a_nested_directory(
    tmp_path: Path,
) -> None:
    _ = _write_project_config(tmp_path, "db_path = 'wiki.db'")
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)

    found = find_project_config(nested)

    assert found == tmp_path / ".llm-wiki" / "config.toml"


def test_reports_invalid_project_config_syntax(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    _ = _write_project_config(tmp_path, "db_path = not-valid-toml")

    with pytest.raises(ConfigReadError):
        _ = resolve_db_path(None, start_path=tmp_path)


def test_explicit_home_expands_the_user_directory() -> None:
    assert resolve_home_path(Path("~/custom-wiki")).is_absolute()


def test_global_mode_project_config_uses_global_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home).mkdir()
    (project / ".llm-wiki").mkdir(parents=True)
    (home / "config.toml").write_text('db_path = "wiki.db"\n', encoding="utf-8")
    (project / ".llm-wiki" / "config.toml").write_text(
        'mode = "global"\nproject_tag = "project:demo"\ndocs_dir = "docs"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))

    assert resolve_db_path(None, project) == home / "wiki.db"
    assert resolve_project_tag(project) == "project:demo"


def test_legacy_db_path_without_mode_stays_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    project = tmp_path / "project"
    (project / ".llm-wiki").mkdir(parents=True)
    (project / ".llm-wiki" / "config.toml").write_text(
        'docs_dir = "docs"\ndb_path = ".llm-wiki/wiki.db"\n',
        encoding="utf-8",
    )

    assert resolve_db_path(None, project) == project / ".llm-wiki" / "wiki.db"


def test_global_mode_ignores_retained_legacy_db_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    _write_project_config(
        project,
        'mode = "global"\nproject_tag = "project:demo"\n'
        'docs_dir = "docs"\ndb_path = ".llm-wiki/wiki.db"\n',
    )
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))

    assert resolve_db_path(None, project) == home / "wiki.db"


def test_isolated_mode_without_db_path_is_rejected(tmp_path: Path) -> None:
    _write_project_config(tmp_path, 'mode = "isolated"\ndocs_dir = "docs"\n')

    with pytest.raises(ConfigReadError):
        _ = resolve_project_config(tmp_path)


def test_unknown_mode_is_rejected(tmp_path: Path) -> None:
    _write_project_config(tmp_path, 'mode = "hybrid"\n')

    with pytest.raises(ConfigReadError):
        _ = resolve_project_config(tmp_path)


def test_malformed_project_tag_is_rejected(tmp_path: Path) -> None:
    _write_project_config(
        tmp_path,
        'mode = "global"\nproject_tag = "Demo Project"\n',
    )

    with pytest.raises(ConfigReadError):
        _ = resolve_project_tag(tmp_path)


def test_project_without_config_has_no_project_tag(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert resolve_project_config(empty) is None
    assert resolve_project_tag(empty) is None


def test_global_home_config_is_not_a_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / ".llm-wiki"
    (home / "docs").mkdir(parents=True)
    (home / "config.toml").write_text(
        'docs_dir = "docs"\ndb_path = "wiki.db"\n', encoding="utf-8"
    )
    monkeypatch.delenv("LLM_WIKI_DB", raising=False)
    monkeypatch.setenv("LLM_WIKI_HOME", str(home))

    assert resolve_project_config(home / "docs") is None
    assert resolve_db_path(None, home / "docs") == home / "wiki.db"
