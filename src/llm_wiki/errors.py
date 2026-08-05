"""Typed errors for LLM Wiki boundaries."""

from dataclasses import dataclass
from pathlib import Path
from typing import override


@dataclass(frozen=True, slots=True)
class WikiError(Exception):
    """Base error surfaced by the CLI."""

    message: str

    @override
    def __str__(self) -> str:
        """Return the CLI-safe error message."""
        return self.message


@dataclass(frozen=True, slots=True)
class DocumentReadError(WikiError):
    """Raised when a Markdown source cannot be read."""

    @classmethod
    def missing(cls, path: Path) -> "DocumentReadError":
        """Build an error for an absent Markdown file."""
        return cls(f"Markdown file does not exist: {path}")

    @classmethod
    def not_file(cls, path: Path) -> "DocumentReadError":
        """Build an error for a non-file Markdown path."""
        return cls(f"Markdown path is not a file: {path}")

    @classmethod
    def unreadable(cls, path: Path) -> "DocumentReadError":
        """Build an error for a Markdown file read failure."""
        return cls(f"Could not read Markdown file: {path}")


@dataclass(frozen=True, slots=True)
class DocumentNotFoundError(WikiError):
    """Raised when a stored document id is absent."""

    @classmethod
    def for_id(cls, document_id: int) -> "DocumentNotFoundError":
        """Build an error for a missing stored document id."""
        return cls(f"Document not found: {document_id}")


@dataclass(frozen=True, slots=True)
class GitRepositoryError(WikiError):
    """Raised when a Git repository is required but absent."""

    @classmethod
    def missing(cls, path: Path) -> "GitRepositoryError":
        """Build an error for a directory that is not a Git repository."""
        return cls(f"Not a git repository: {path}")


@dataclass(frozen=True, slots=True)
class ConfigReadError(WikiError):
    """Raised when an LLM Wiki config exists but cannot be used."""

    @classmethod
    def invalid(cls, path: Path) -> "ConfigReadError":
        """Build an error for invalid configuration syntax."""
        return cls(f"Invalid LLM Wiki config: {path}")

    @classmethod
    def unreadable(cls, path: Path) -> "ConfigReadError":
        """Build an error for unreadable configuration."""
        return cls(f"Could not read LLM Wiki config: {path}")


@dataclass(frozen=True, slots=True)
class EmbeddingBackendError(WikiError):
    """Raised when the configured embedding server cannot be used.

    Callers treat this as "fall back to BM25", never as a fatal condition: a
    wiki must stay searchable when the model server is down.
    """

    @classmethod
    def no_endpoint(cls) -> "EmbeddingBackendError":
        """Build an error for embedding settings with no endpoint."""
        return cls("No embedding endpoint configured")

    @classmethod
    def bad_scheme(cls, scheme: str) -> "EmbeddingBackendError":
        """Build an error for a non-HTTP embedding endpoint."""
        return cls(f"Embedding endpoint must be http or https, got: {scheme or 'none'}")

    @classmethod
    def unreachable(cls, url: str, reason: str) -> "EmbeddingBackendError":
        """Build an error for an embedding server that could not be reached."""
        return cls(f"Embedding server unreachable at {url}: {reason}")

    @classmethod
    def malformed(cls, url: str) -> "EmbeddingBackendError":
        """Build an error for an unreadable embedding response."""
        return cls(f"Embedding server returned an unreadable response: {url}")

    @classmethod
    def count_mismatch(cls, expected: int, received: int) -> "EmbeddingBackendError":
        """Build an error for a reply that does not cover every input text."""
        return cls(f"Embedding server returned {received} vectors for {expected} texts")

    @classmethod
    def wrong_dimension(cls, expected: int, received: int) -> "EmbeddingBackendError":
        """Build an error for a vector of unexpected width."""
        return cls(f"Embedding dimension mismatch: expected {expected}, got {received}")


@dataclass(frozen=True, slots=True)
class SqlColumnTypeError(WikiError):
    """Raised when SQLite returns an unexpected column type."""

    @classmethod
    def expected_integer(cls, index: int) -> "SqlColumnTypeError":
        """Build an error for a non-integer SQLite column."""
        return cls(f"Expected integer column at index {index}")

    @classmethod
    def expected_text(cls, index: int) -> "SqlColumnTypeError":
        """Build an error for a non-text SQLite column."""
        return cls(f"Expected text column at index {index}")
