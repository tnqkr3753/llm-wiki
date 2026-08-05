"""Tests for the HTTP embedding backend."""

import json
from pathlib import Path
from typing import Self
from urllib.request import Request

import pytest

from llm_wiki.embedding import (
    EmbeddingSettings,
    HttpEmbeddingProvider,
    describe_settings,
    load_provider,
    resolve_embedding_settings,
)
from llm_wiki.errors import EmbeddingBackendError

REFUSED = "connection refused"


class _FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Recorder:
    """Stand in for urlopen, capturing one request and replaying one payload."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.url: str = ""
        self.body: dict[str, object] = {}
        self.headers: dict[str, str] = {}
        self.calls = 0

    def __call__(self, request: Request, timeout: float = 0.0) -> _FakeResponse:
        self.calls += 1
        self.url = request.full_url
        assert isinstance(request.data, bytes)
        self.body = json.loads(request.data.decode("utf-8"))
        self.headers = dict(request.headers)
        return _FakeResponse(self.payload)


OLLAMA_REPLY = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
OPENAI_REPLY = {
    "data": [
        {"index": 1, "embedding": [0.3, 0.4]},
        {"index": 0, "embedding": [0.1, 0.2]},
    ]
}


def _install(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    monkeypatch.setattr("llm_wiki.embedding.urlopen", recorder)


def test_an_ollama_endpoint_posts_to_the_embed_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(OLLAMA_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="bge-m3", endpoint="http://127.0.0.1:11434")
    )

    vectors = provider.embed(["a", "b"])

    assert recorder.url == "http://127.0.0.1:11434/api/embed"
    assert recorder.body == {"model": "bge-m3", "input": ["a", "b"]}
    assert vectors == ((0.1, 0.2), (0.3, 0.4))


def test_a_v1_endpoint_uses_the_openai_dialect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(OPENAI_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="bge-m3", endpoint="http://127.0.0.1:8000/v1")
    )

    vectors = provider.embed(["a", "b"])

    assert recorder.url == "http://127.0.0.1:8000/v1/embeddings"
    assert vectors == ((0.1, 0.2), (0.3, 0.4))


def test_openai_results_are_reordered_by_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An out-of-order `data` array must not silently mismatch text to vector."""
    recorder = _Recorder(OPENAI_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:8000/v1", api="openai")
    )

    assert provider.embed(["first", "second"]) == ((0.1, 0.2), (0.3, 0.4))


def test_an_explicit_api_setting_overrides_url_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(OPENAI_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:9999", api="openai")
    )

    _ = provider.embed(["a", "b"])

    assert recorder.url == "http://127.0.0.1:9999/v1/embeddings"


def test_an_endpoint_naming_the_route_is_used_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(OLLAMA_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:8080/api/embed")
    )

    _ = provider.embed(["a", "b"])

    assert recorder.url == "http://127.0.0.1:8080/api/embed"


def test_an_api_key_is_sent_as_a_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(OPENAI_REPLY)
    _install(monkeypatch, recorder)
    monkeypatch.setenv("LLM_WIKI_EMBED_API_KEY", "sk-test")
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:8000/v1")
    )

    _ = provider.embed(["a", "b"])

    assert recorder.headers.get("Authorization") == "Bearer sk-test"


def test_embedding_no_texts_makes_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(OLLAMA_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434")
    )

    assert provider.embed([]) == ()
    assert recorder.calls == 0


def test_a_short_reply_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder({"embeddings": [[0.1, 0.2]]})
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434")
    )

    with pytest.raises(EmbeddingBackendError):
        _ = provider.embed(["a", "b"])


def test_a_malformed_reply_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder({"unexpected": True})
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434")
    )

    with pytest.raises(EmbeddingBackendError):
        _ = provider.embed(["a"])


def test_a_wrong_dimension_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(OLLAMA_REPLY)
    _install(monkeypatch, recorder)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434", dimension=1024)
    )

    with pytest.raises(EmbeddingBackendError):
        _ = provider.embed(["a", "b"])


def test_large_inputs_are_sent_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Batching:
        def __init__(self) -> None:
            self.sizes: list[int] = []

        def __call__(self, request: Request, timeout: float = 0.0) -> _FakeResponse:
            assert isinstance(request.data, bytes)
            body = json.loads(request.data.decode("utf-8"))
            texts: list[str] = body["input"]
            self.sizes.append(len(texts))
            return _FakeResponse({"embeddings": [[0.0] for _ in texts]})

    batching = _Batching()
    monkeypatch.setattr("llm_wiki.embedding.urlopen", batching)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434"),
        batch_size=8,
    )

    vectors = provider.embed([f"text {index}" for index in range(20)])

    assert batching.sizes == [8, 8, 4]
    assert len(vectors) == 20


def test_a_transport_failure_becomes_a_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(request: Request, timeout: float = 0.0) -> _FakeResponse:
        raise OSError(REFUSED)

    monkeypatch.setattr("llm_wiki.embedding.urlopen", _boom)
    provider = HttpEmbeddingProvider(
        EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434")
    )

    with pytest.raises(EmbeddingBackendError):
        _ = provider.embed(["a"])


def test_load_provider_needs_an_endpoint(tmp_path: Path) -> None:
    settings = EmbeddingSettings(model="bge-m3")

    assert load_provider(settings) is None
    assert "no endpoint" in describe_settings(settings)
    assert tmp_path.exists()


def test_load_provider_refuses_a_blocked_remote_endpoint() -> None:
    settings = EmbeddingSettings(model="m", endpoint="http://remote.example:11434")

    assert load_provider(settings) is None


def test_load_provider_returns_a_provider_for_a_local_endpoint() -> None:
    settings = EmbeddingSettings(model="m", endpoint="http://127.0.0.1:11434")

    assert isinstance(load_provider(settings), HttpEmbeddingProvider)


def test_describe_settings_reports_a_ready_backend() -> None:
    settings = EmbeddingSettings(
        model="bge-m3", endpoint="http://127.0.0.1:11434", dimension=1024
    )

    described = describe_settings(settings)

    assert "bge-m3" in described
    assert "no backend installed yet" not in described


def test_the_api_dialect_resolves_from_the_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_WIKI_EMBED_MODEL", "m")
    monkeypatch.setenv("LLM_WIKI_EMBED_API", "openai")
    monkeypatch.setenv("LLM_WIKI_HOME", str(tmp_path / "home"))

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert settings.api == "openai"


def test_an_api_key_never_comes_from_a_config_file(tmp_path: Path) -> None:
    """A committed config must not be a place secrets can hide."""
    config_dir = tmp_path / ".llm-wiki"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[embedding]\nmodel = "m"\napi_key = "sk-leaked"\n', encoding="utf-8"
    )

    settings = resolve_embedding_settings(start_path=tmp_path)

    assert settings is not None
    assert "sk-leaked" not in describe_settings(settings)
    assert not hasattr(settings, "api_key")
