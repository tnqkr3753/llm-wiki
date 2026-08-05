"""Domain models for indexed wiki documents."""

from dataclasses import dataclass
from typing import NewType

DocumentId = NewType("DocumentId", int)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """A Markdown document parsed at the filesystem boundary."""

    path: str
    title: str
    tags: tuple[str, ...]
    body: str
    links: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """A document loaded from the SQLite index."""

    id: DocumentId
    path: str
    title: str
    tags: tuple[str, ...]
    body: str


@dataclass(frozen=True, slots=True)
class DocumentUsage:
    """How often one indexed document has been retrieved for grounding."""

    id: DocumentId
    path: str
    title: str
    retrieved_count: int
    last_retrieved_at: str | None


@dataclass(frozen=True, slots=True)
class ReindexFailure:
    """One document that could not be indexed during a directory reindex."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReindexResult:
    """Outcome of reindexing every Markdown file under one root."""

    indexed: int
    removed: int
    failures: tuple[ReindexFailure, ...]


@dataclass(frozen=True, slots=True)
class DocumentLink:
    """One indexed document reached from or pointing to another document."""

    id: DocumentId
    path: str
    title: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A ranked result from the full-text index."""

    id: DocumentId
    path: str
    title: str
    tags: tuple[str, ...]
    snippet: str


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """One heading-scoped slice of a document body, as embedded and indexed."""

    ordinal: int
    heading: str
    text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class EmbedResult:
    """Outcome of one incremental embedding pass over the chunk cache."""

    embedded: int
    reused: int
    failed: int
    reason: str | None
