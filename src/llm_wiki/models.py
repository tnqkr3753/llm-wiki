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


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """A document loaded from the SQLite index."""

    id: DocumentId
    path: str
    title: str
    tags: tuple[str, ...]
    body: str


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
class SearchResult:
    """A ranked result from the full-text index."""

    id: DocumentId
    path: str
    title: str
    tags: tuple[str, ...]
    snippet: str
