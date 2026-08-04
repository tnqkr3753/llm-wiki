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

    @classmethod
    def invalid_slug(cls, name: str) -> "ConfigReadError":
        """Build an error for a directory name with no usable project slug."""
        return cls(f"Cannot derive a project slug from: {name}")


@dataclass(frozen=True, slots=True)
class VaultError(WikiError):
    """Raised when global vault planning or application must stop."""

    @classmethod
    def duplicate_slug(cls, slug: str) -> "VaultError":
        """Build an error for a project slug used by two sources."""
        return cls(f"Duplicate project slug: {slug}")

    @classmethod
    def invalid_source_slug(cls, slug: str) -> "VaultError":
        """Build an error for a source slug that is not a valid project slug."""
        return cls(f"Invalid project slug: {slug}")

    @classmethod
    def missing_root(cls, path: Path) -> "VaultError":
        """Build an error for a source docs root that is not a directory."""
        return cls(f"Source docs root is not a directory: {path}")

    @classmethod
    def conflicts_block_apply(cls, count: int) -> "VaultError":
        """Build an error refusing to apply a plan with conflicts."""
        return cls(f"Refusing to apply: {count} unmanaged target conflict(s)")

    @classmethod
    def invalid_source_spec(cls, spec: str) -> "VaultError":
        """Build an error for a malformed slug=/abs/docs source mapping."""
        return cls(f"Invalid --source mapping (expected slug=/abs/docs): {spec}")


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
