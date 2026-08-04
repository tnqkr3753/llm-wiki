"""Configuration resolution for LLM Wiki paths."""

import os
import re
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from llm_wiki.errors import ConfigReadError

ENV_WIKI_DB: Final = "LLM_WIKI_DB"
ENV_WIKI_HOME: Final = "LLM_WIKI_HOME"
PROJECT_CONFIG: Final = Path(".llm-wiki/config.toml")
GLOBAL_HOME: Final = Path("~/.llm-wiki")
PROJECT_TAG_PREFIX: Final = "project:"
PROJECT_SLUG_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")


class WikiMode(StrEnum):
    """How a project stores and retrieves wiki knowledge."""

    GLOBAL = "global"
    ISOLATED = "isolated"


@dataclass(frozen=True, slots=True)
class ProjectWikiConfig:
    """Parsed project-local LLM Wiki configuration."""

    root: Path
    mode: WikiMode
    docs_dir: Path
    project_tag: str | None
    db_path: Path | None


def resolve_db_path(explicit_db: Path | None, start_path: Path | None = None) -> Path:
    """Resolve the DB path from CLI, env, project config, or global config."""
    if explicit_db is not None:
        return explicit_db

    env_db = os.environ.get(ENV_WIKI_DB)
    if env_db is not None and env_db.strip() != "":
        return Path(env_db).expanduser()

    project_config = resolve_project_config(start_path)
    if (
        project_config is not None
        and project_config.mode is WikiMode.ISOLATED
        and project_config.db_path is not None
    ):
        return project_config.db_path

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


def resolve_project_config(start_path: Path | None = None) -> ProjectWikiConfig | None:
    """Read the nearest project config; legacy db_path-only files are isolated."""
    search_start = Path.cwd() if start_path is None else start_path
    config_path = find_project_config(search_start)
    if config_path is None:
        return None

    # Working inside the global home (a directory literally named .llm-wiki)
    # makes the upward scan hit the *global* config. That file configures the
    # home, not a project — treating it as one would resolve its relative
    # db_path against the home's parent directory.
    global_config = resolve_home_path(None) / "config.toml"
    if config_path.resolve() == global_config.resolve():
        return None

    data = _load_config(config_path)
    root = config_path.parent.parent

    raw_db = _optional_string(data, "db_path", config_path)
    raw_mode = _optional_string(data, "mode", config_path)
    raw_tag = _optional_string(data, "project_tag", config_path)
    raw_docs = _optional_string(data, "docs_dir", config_path)

    if raw_mode is None:
        mode = WikiMode.ISOLATED if raw_db is not None else WikiMode.GLOBAL
    else:
        try:
            mode = WikiMode(raw_mode)
        except ValueError as exc:
            raise ConfigReadError.invalid(config_path) from exc

    if mode is WikiMode.ISOLATED and raw_db is None:
        raise ConfigReadError.invalid(config_path)

    if raw_tag is not None and not _is_valid_project_tag(raw_tag):
        raise ConfigReadError.invalid(config_path)

    docs_dir = _resolve_relative(root, raw_docs if raw_docs is not None else "docs")
    db_path = None if raw_db is None else _resolve_relative(root, raw_db)
    return ProjectWikiConfig(
        root=root,
        mode=mode,
        docs_dir=docs_dir,
        project_tag=raw_tag,
        db_path=db_path,
    )


def resolve_project_tag(start_path: Path | None = None) -> str | None:
    """Return the validated project tag configured for the nearest project."""
    config = resolve_project_config(start_path)
    return None if config is None else config.project_tag


def normalize_project_slug(name: str) -> str:
    """Derive a valid project slug from a directory name."""
    lowered = name.strip().lower()
    collapsed = re.sub(r"[^a-z0-9._-]+", "-", lowered)
    slug = collapsed.lstrip("._-")
    if not PROJECT_SLUG_PATTERN.fullmatch(slug):
        raise ConfigReadError.invalid_slug(name)
    return slug


def find_project_config(start_path: Path) -> Path | None:
    """Find the nearest project-local LLM Wiki config."""
    start = start_path if start_path.is_dir() else start_path.parent
    for candidate_root in (start, *start.parents):
        config_path = candidate_root / PROJECT_CONFIG
        if config_path.is_file():
            return config_path
    return None


def _is_valid_project_tag(tag: str) -> bool:
    if not tag.startswith(PROJECT_TAG_PREFIX):
        return False
    slug = tag[len(PROJECT_TAG_PREFIX) :]
    return PROJECT_SLUG_PATTERN.fullmatch(slug) is not None


def _load_config(config_path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigReadError.unreadable(config_path) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigReadError.invalid(config_path) from exc


def _optional_string(
    data: dict[str, object], key: str, config_path: Path
) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigReadError.invalid(config_path)
    stripped = value.strip()
    return stripped if stripped != "" else None


def _read_db_path(config_path: Path) -> str | None:
    if not config_path.is_file():
        return None
    data = _load_config(config_path)
    value = data.get("db_path")
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _resolve_relative(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return root / path
