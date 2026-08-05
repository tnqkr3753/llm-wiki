"""Wiring between resolved embedding settings and the retrieval primitives.

Kept apart from ``store`` so the index stays ignorant of embeddings, and apart
from ``embedding`` so the transport stays ignorant of the database. Every
function here answers the same question — is semantic retrieval available right
now? — and every one of them answers "no" rather than raising.
"""

from pathlib import Path

from llm_wiki.embedding import (
    EmbeddingProvider,
    EmbeddingSettings,
    load_provider,
    resolve_embedding_settings,
)
from llm_wiki.errors import WikiError
from llm_wiki.models import EmbedResult
from llm_wiki.semantic import (
    SemanticSearch,
    embed_missing_chunks,
    make_semantic_search,
    prune_orphan_embeddings,
)


def active_backend(
    start_path: Path | None = None,
) -> tuple[EmbeddingSettings, EmbeddingProvider] | None:
    """Resolve settings and a usable provider, or None if embedding is off.

    A malformed config is reported by ``doctor``; here it simply means no
    semantic retrieval, because a broken embedding setting must never stop a
    wiki from being searched.
    """
    try:
        settings = resolve_embedding_settings(start_path)
    except WikiError:
        return None
    if settings is None:
        return None
    provider = load_provider(settings)
    if provider is None:
        return None
    return (settings, provider)


def build_semantic_search(db_path: Path, query: str) -> SemanticSearch | None:
    """Build the semantic side of retrieval, if a backend is available."""
    backend = active_backend()
    if backend is None:
        return None
    settings, provider = backend
    return make_semantic_search(db_path, query, provider, settings.model)


def refresh_embeddings(db_path: Path) -> EmbedResult | None:
    """Embed what changed and drop what no longer exists.

    Returns None when embedding is not configured, which is the common case and
    not a failure.
    """
    backend = active_backend()
    if backend is None:
        return None
    settings, provider = backend
    result = embed_missing_chunks(db_path, provider, settings.model)
    _ = prune_orphan_embeddings(db_path)
    return result
