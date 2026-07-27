"""Embedding configuration surface.

LLM Wiki retrieves with SQLite FTS5 today. This module resolves where a local
embedding model *would* come from and defines the contract a backend must
satisfy, so semantic search can be added later without changing the
configuration surface, the CLI, or user documentation again.

Nothing here touches retrieval: with no backend installed, `load_provider()`
returns `None` and search stays pure BM25.
"""

import os
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast, runtime_checkable
from urllib.parse import urlparse

from llm_wiki.config import find_project_config, resolve_home_path
from llm_wiki.errors import ConfigReadError

ENV_EMBED_MODEL: Final = "LLM_WIKI_EMBED_MODEL"
ENV_EMBED_URL: Final = "LLM_WIKI_EMBED_URL"
ENV_EMBED_DIM: Final = "LLM_WIKI_EMBED_DIM"
ENV_EMBED_ALLOW_REMOTE: Final = "LLM_WIKI_EMBED_ALLOW_REMOTE"

CONFIG_SECTION: Final = "embedding"
LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", ""})
TRUE_VALUES: Final = frozenset({"1", "true", "yes", "on"})


@runtime_checkable
class EmbeddingProvider(Protocol):
    """What a backend must offer for LLM Wiki to embed text.

    Deliberately minimal: one call, text in, vectors out, in the same order.
    Chunking, storage, and ranking stay on the LLM Wiki side.
    """

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input text, in input order."""
        ...


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    """Where embeddings would come from, once a backend exists."""

    model: str
    endpoint: str | None = None
    dimension: int | None = None
    allow_remote: bool = False

    @property
    def is_remote(self) -> bool:
        """Report whether the endpoint leaves this machine."""
        if self.endpoint is None:
            return False
        return urlparse(self.endpoint).hostname not in LOOPBACK_HOSTS

    @property
    def is_blocked(self) -> bool:
        """Report whether these settings are refused for privacy reasons.

        Wiki documents are internal decisions and runbooks. Sending them to a
        host the user did not explicitly approve is not a default worth having.
        """
        return self.is_remote and not self.allow_remote


def resolve_embedding_settings(
    start_path: Path | None = None,
) -> EmbeddingSettings | None:
    """Resolve embedding settings from the environment, then config files.

    Each field resolves independently, so an endpoint in project config can be
    combined with a model name from the environment. Returns None when no model
    is configured anywhere, which is the default state.
    """
    file_values = _config_section(start_path)

    model = _first_str(os.environ.get(ENV_EMBED_MODEL), file_values.get("model"))
    if model is None:
        return None

    return EmbeddingSettings(
        model=model,
        endpoint=_first_str(os.environ.get(ENV_EMBED_URL), file_values.get("endpoint")),
        dimension=_first_int(
            os.environ.get(ENV_EMBED_DIM), file_values.get("dimension")
        ),
        allow_remote=_first_bool(
            os.environ.get(ENV_EMBED_ALLOW_REMOTE), file_values.get("allow_remote")
        ),
    )


def load_provider(settings: EmbeddingSettings) -> EmbeddingProvider | None:
    """Load the embedding backend for these settings, if one is installed.

    No backend ships yet, so this always returns None and callers fall back to
    BM25. Blocked settings never load, even once a backend exists.
    """
    if settings.is_blocked:
        return None
    return None


def describe_settings(settings: EmbeddingSettings | None) -> str:
    """Summarize embedding configuration for diagnostics."""
    if settings is None:
        return "Not configured (BM25 only)"
    if settings.is_blocked:
        return (
            f"{settings.model} - remote endpoint blocked "
            f"({settings.endpoint}); set {ENV_EMBED_ALLOW_REMOTE}=1 to allow"
        )
    where = settings.endpoint or "local model"
    dimension = "" if settings.dimension is None else f", dim {settings.dimension}"
    return f"{settings.model} via {where}{dimension} - no backend installed yet"


def _config_section(start_path: Path | None) -> dict[str, object]:
    """Read the [embedding] table from the project or global config."""
    search_start = Path.cwd() if start_path is None else start_path
    project_config = find_project_config(search_start)
    if project_config is not None:
        section = _read_section(project_config)
        if section:
            return section
    return _read_section(resolve_home_path(None) / "config.toml")


def _read_section(config_path: Path) -> dict[str, object]:
    if not config_path.is_file():
        return {}
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigReadError.unreadable(config_path) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigReadError.invalid(config_path) from exc

    section = data.get(CONFIG_SECTION)
    if not isinstance(section, dict):
        return {}
    # TOML table keys are always strings; values stay untrusted and each
    # accessor below validates the type it needs.
    return cast("dict[str, object]", section)


def _first_str(*candidates: object) -> str | None:
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip() != "":
            return candidate.strip()
    return None


def _first_int(*candidates: object) -> int | None:
    for candidate in candidates:
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, int):
            return candidate
        if isinstance(candidate, str) and candidate.strip().isdigit():
            return int(candidate.strip())
    return None


def _first_bool(*candidates: object) -> bool:
    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, str) and candidate.strip() != "":
            return candidate.strip().lower() in TRUE_VALUES
    return False
