"""Embedding configuration and the HTTP backend that satisfies it.

LLM Wiki resolves where a local embedding model comes from, then talks to it
over HTTP with the standard library only — no torch, no sentence-transformers,
so `uv tool install` stays a seconds-long download. An in-process backend, if
one is ever wanted, still belongs behind an optional extra.

Absence is never an error: with no model configured, no endpoint, or a blocked
remote host, `load_provider()` returns `None` and retrieval stays pure BM25.
"""

import json
import os
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast, final, runtime_checkable
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from llm_wiki.config import find_project_config, resolve_home_path
from llm_wiki.errors import ConfigReadError, EmbeddingBackendError

ENV_EMBED_MODEL: Final = "LLM_WIKI_EMBED_MODEL"
ENV_EMBED_URL: Final = "LLM_WIKI_EMBED_URL"
ENV_EMBED_DIM: Final = "LLM_WIKI_EMBED_DIM"
ENV_EMBED_ALLOW_REMOTE: Final = "LLM_WIKI_EMBED_ALLOW_REMOTE"
ENV_EMBED_API: Final = "LLM_WIKI_EMBED_API"
# Read from the environment only, never from config: a wiki's config.toml is
# routinely committed, and a key that can live there eventually does.
ENV_EMBED_API_KEY: Final = "LLM_WIKI_EMBED_API_KEY"

CONFIG_SECTION: Final = "embedding"
LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", ""})
TRUE_VALUES: Final = frozenset({"1", "true", "yes", "on"})

API_OLLAMA: Final = "ollama"
API_OPENAI: Final = "openai"
OLLAMA_ROUTE: Final = "/api/embed"
OPENAI_ROUTE: Final = "/v1/embeddings"
ROUTE_SUFFIXES: Final = ("/embed", "/embeddings")
DEFAULT_BATCH_SIZE: Final = 32
DEFAULT_TIMEOUT_SECONDS: Final = 60.0


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
    api: str | None = None

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
        api=_first_str(os.environ.get(ENV_EMBED_API), file_values.get("api")),
    )


@final
class HttpEmbeddingProvider:
    """Embed text through an HTTP embedding server.

    Speaks the two dialects local servers actually offer: Ollama's
    ``/api/embed`` and the OpenAI-compatible ``/v1/embeddings`` that vLLM,
    llama.cpp, LM Studio, and TEI all expose. Both take the same request body,
    so only the route and the reply shape differ.
    """

    def __init__(
        self,
        settings: EmbeddingSettings,
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Bind a provider to resolved settings and its transport limits."""
        self._settings = settings
        self._batch_size = max(1, batch_size)
        self._timeout = timeout
        self._url = _resolve_url(settings)

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input text, in input order."""
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._embed_batch(batch))
        return tuple(vectors)

    def _embed_batch(self, batch: Sequence[str]) -> list[tuple[float, ...]]:
        payload = json.dumps(
            {"model": self._settings.model, "input": list(batch)}
        ).encode("utf-8")
        request = Request(  # noqa: S310 - scheme is validated in _resolve_url
            self._url,
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, TimeoutError) as exc:
            raise EmbeddingBackendError.unreachable(self._url, str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingBackendError.malformed(self._url) from exc

        vectors = _parse_vectors(body, self._url)
        if len(vectors) != len(batch):
            raise EmbeddingBackendError.count_mismatch(len(batch), len(vectors))
        self._check_dimension(vectors)
        return vectors

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get(ENV_EMBED_API_KEY, "").strip()
        if api_key != "":
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _check_dimension(self, vectors: list[tuple[float, ...]]) -> None:
        expected = self._settings.dimension
        if expected is None:
            return
        for vector in vectors:
            if len(vector) != expected:
                raise EmbeddingBackendError.wrong_dimension(expected, len(vector))


def _resolve_dialect(settings: EmbeddingSettings) -> str:
    """Pick the request dialect: an explicit setting, else the endpoint shape."""
    if settings.api is not None:
        return settings.api.strip().lower()
    endpoint = settings.endpoint or ""
    return API_OPENAI if "/v1" in urlparse(endpoint).path else API_OLLAMA


def _resolve_url(settings: EmbeddingSettings) -> str:
    """Build the full embedding URL from a base endpoint.

    An endpoint that already names an embedding route is used verbatim, so a
    server on a nonstandard path stays reachable without a new config key.
    """
    endpoint = (settings.endpoint or "").rstrip("/")
    if endpoint == "":
        raise EmbeddingBackendError.no_endpoint()
    scheme = urlparse(endpoint).scheme
    if scheme not in {"http", "https"}:
        raise EmbeddingBackendError.bad_scheme(scheme)
    if endpoint.endswith(ROUTE_SUFFIXES):
        return endpoint
    if _resolve_dialect(settings) == API_OPENAI:
        return f"{endpoint.removesuffix('/v1')}{OPENAI_ROUTE}"
    return f"{endpoint}{OLLAMA_ROUTE}"


def _parse_vectors(body: object, url: str) -> list[tuple[float, ...]]:
    """Read vectors out of either dialect's reply, in input order.

    Dispatch is on the reply's own shape rather than the configured dialect, so
    a server that answers in the other format still works.
    """
    if not isinstance(body, dict):
        raise EmbeddingBackendError.malformed(url)
    payload = cast("dict[str, object]", body)

    raw = payload.get("embeddings")
    if isinstance(raw, list):
        return [_coerce_vector(item, url) for item in cast("list[object]", raw)]

    data = payload.get("data")
    if isinstance(data, list):
        # The OpenAI schema does not promise response order, and an out-of-order
        # array would silently pair each text with another text's vector.
        ordered = sorted(cast("list[object]", data), key=_entry_index)
        return [_coerce_vector(_entry_embedding(item), url) for item in ordered]

    raise EmbeddingBackendError.malformed(url)


def _entry_embedding(item: object) -> object:
    if not isinstance(item, dict):
        return None
    return cast("dict[str, object]", item).get("embedding")


def _entry_index(item: object) -> int:
    if isinstance(item, dict):
        index = cast("dict[str, object]", item).get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            return index
    return 0


def _coerce_vector(item: object, url: str) -> tuple[float, ...]:
    if not isinstance(item, list):
        raise EmbeddingBackendError.malformed(url)
    values = cast("list[object]", item)
    if not all(isinstance(value, (int, float)) for value in values):
        raise EmbeddingBackendError.malformed(url)
    return tuple(float(cast("float", value)) for value in values)


def load_provider(settings: EmbeddingSettings) -> EmbeddingProvider | None:
    """Load the embedding backend for these settings, if one is usable.

    Returns None — never raises — when embedding is off, unreachable by
    configuration, or refused for privacy, because every caller's fallback is
    to keep searching with BM25.
    """
    if settings.is_blocked or settings.endpoint is None:
        return None
    try:
        return HttpEmbeddingProvider(settings)
    except EmbeddingBackendError:
        return None


def describe_settings(settings: EmbeddingSettings | None) -> str:
    """Summarize embedding configuration for diagnostics.

    The endpoint is shown with any credentials stripped: `doctor` output is
    routinely pasted into issues and logs, so a `user:password@host` or a
    `?token=` query must never leave the machine through a diagnostic.
    """
    if settings is None:
        return "Not configured (BM25 only)"
    if settings.is_blocked:
        return (
            f"{settings.model} - remote endpoint blocked "
            f"({_display_endpoint(settings.endpoint or '')}); "
            f"set {ENV_EMBED_ALLOW_REMOTE}=1 to allow"
        )
    if settings.endpoint is None:
        return (
            f"{settings.model} - no endpoint configured; "
            f"set {ENV_EMBED_URL} to a local embedding server"
        )
    dimension = "" if settings.dimension is None else f", dim {settings.dimension}"
    return (
        f"{settings.model} via {_display_endpoint(settings.endpoint)} "
        f"({_resolve_dialect(settings)}){dimension}"
    )


def _display_endpoint(endpoint: str) -> str:
    """Render an endpoint for humans without its userinfo, query, or fragment."""
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def _config_section(start_path: Path | None) -> dict[str, object]:
    """Merge the [embedding] table from global, then project, per field.

    Project keys override global keys, and each field then resolves
    independently against the environment in ``resolve_embedding_settings`` —
    so the documented environment -> project -> global precedence holds per
    field, not per whole section.
    """
    search_start = Path.cwd() if start_path is None else start_path
    global_section = _read_section(resolve_home_path(None) / "config.toml")
    project_config = find_project_config(search_start)
    project_section = {} if project_config is None else _read_section(project_config)
    return {**global_section, **project_section}


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
