"""Configuration resolution for LLM Wiki paths."""

import os
import tomllib
from pathlib import Path
from typing import Final

from llm_wiki.errors import ConfigReadError

ENV_WIKI_DB: Final = "LLM_WIKI_DB"
ENV_WIKI_HOME: Final = "LLM_WIKI_HOME"
PROJECT_CONFIG: Final = Path(".llm-wiki/config.toml")
GLOBAL_HOME: Final = Path("~/.llm-wiki")


def resolve_db_path(explicit_db: Path | None, start_path: Path | None = None) -> Path:
    """Resolve the DB path from CLI, env, project config, or global config."""
    if explicit_db is not None:
        return explicit_db

    env_db = os.environ.get(ENV_WIKI_DB)
    if env_db is not None and env_db.strip() != "":
        return Path(env_db).expanduser()

    search_start = Path.cwd() if start_path is None else start_path
    project_config = find_project_config(search_start)
    if project_config is not None:
        configured_db = _read_db_path(project_config)
        if configured_db is not None:
            return _resolve_relative(project_config.parent.parent, configured_db)

    home_path = resolve_home_path(None)
    configured_global_db = _read_db_path(home_path / "config.toml")
    if configured_global_db is not None:
        return _resolve_relative(home_path, configured_global_db)
    return home_path / "wiki.db"


def resolve_home_path(explicit_home: Path | None) -> Path:
    """Resolve the global LLM Wiki home directory."""
    if explicit_home is not None:
        return explicit_home.expanduser()
    env_home = os.environ.get(ENV_WIKI_HOME)
    if env_home is not None and env_home.strip() != "":
        return Path(env_home).expanduser()
    return GLOBAL_HOME.expanduser()


def find_project_config(start_path: Path) -> Path | None:
    """Find the nearest project-local LLM Wiki config."""
    start = start_path if start_path.is_dir() else start_path.parent
    for candidate_root in (start, *start.parents):
        config_path = candidate_root / PROJECT_CONFIG
        if config_path.is_file():
            return config_path
    return None


def _read_db_path(config_path: Path) -> str | None:
    if not config_path.is_file():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigReadError.unreadable(config_path) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigReadError.invalid(config_path) from exc

    value = data.get("db_path")
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _resolve_relative(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return root / path
