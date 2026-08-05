"""Heading-level chunking of Markdown bodies.

One vector per document is vaguely similar to every query, so embedding whole
documents wastes the effort. Splitting on headings gives each chunk a single
subject, and it pays off under BM25 too: a search result can quote the section
that actually matched instead of a fixed-width fragment.
"""

import hashlib
import re
from typing import Final

from llm_wiki.models import DocumentChunk

# Chosen against the 512-token context of the common local embedding models
# (bge-*, e5-*, nomic-embed). At roughly 2 characters per token for Korean and
# 4 for English, 1200 characters stays inside the window either way.
DEFAULT_MAX_CHARS: Final = 1200

HEADING_PATTERN: Final = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_PATTERN: Final = re.compile(r"^\s*(?:```|~~~)")
HEADING_SEPARATOR: Final = " > "


def split_into_chunks(
    body: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[DocumentChunk, ...]:
    """Split a Markdown body into heading-scoped chunks, in document order.

    Each chunk's text is prefixed with its heading path (``Parent > Child``) so
    the embedded text carries the context that the section body alone omits.
    Sections longer than ``max_chars`` are split further at paragraph breaks,
    and empty sections are dropped.
    """
    chunks: list[DocumentChunk] = []
    for heading, section_body in _iter_sections(body):
        for text in _fit_to_cap(heading, section_body, max_chars):
            chunks.append(
                DocumentChunk(
                    ordinal=len(chunks),
                    heading=heading,
                    text=text,
                    content_hash=chunk_hash(text),
                )
            )
    return tuple(chunks)


def chunk_hash(text: str) -> str:
    """Hash chunk text so unchanged chunks can skip re-embedding."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iter_sections(body: str) -> list[tuple[str, str]]:
    """Group lines into (heading path, section body) pairs, preamble first."""
    sections: list[tuple[str, str]] = []
    path: list[tuple[int, str]] = []
    heading = ""
    lines: list[str] = []
    in_fence = False

    for line in body.splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            lines.append(line)
            continue

        match = None if in_fence else HEADING_PATTERN.match(line)
        if match is None:
            lines.append(line)
            continue

        sections.append((heading, "\n".join(lines).strip()))
        path = _push_heading(path, len(match.group(1)), match.group(2).strip())
        heading = HEADING_SEPARATOR.join(title for _, title in path)
        lines = []

    sections.append((heading, "\n".join(lines).strip()))
    return [(name, text) for name, text in sections if text != ""]


def _push_heading(
    path: list[tuple[int, str]],
    level: int,
    title: str,
) -> list[tuple[int, str]]:
    """Return the heading path with this heading placed at its own level.

    Every ancestor at the same or a deeper level is dropped, so a sibling
    section never inherits its predecessor's subsections. Levels are kept
    alongside the titles because a document may start at ``##`` or skip a
    level, which makes list position an unreliable stand-in for depth.
    """
    return [*[entry for entry in path if entry[0] < level], (level, title)]


def _fit_to_cap(heading: str, section_body: str, max_chars: int) -> list[str]:
    """Render one section as chunk texts that each fit within ``max_chars``."""
    prefix = "" if heading == "" else f"{heading}\n\n"
    whole = f"{prefix}{section_body}"
    if len(whole) <= max_chars:
        return [whole]

    budget = max(1, max_chars - len(prefix))
    return [f"{prefix}{piece}" for piece in _split_body(section_body, budget)]


def _split_body(section_body: str, budget: int) -> list[str]:
    """Pack paragraphs into pieces of at most ``budget`` characters."""
    pieces: list[str] = []
    current = ""
    for paragraph in _iter_paragraphs(section_body, budget):
        candidate = paragraph if current == "" else f"{current}\n\n{paragraph}"
        if len(candidate) <= budget:
            current = candidate
            continue
        if current != "":
            pieces.append(current)
        current = paragraph
    if current != "":
        pieces.append(current)
    return pieces


def _iter_paragraphs(section_body: str, budget: int) -> list[str]:
    """Split into paragraphs, hard-splitting any single one that overflows."""
    paragraphs: list[str] = []
    for raw in re.split(r"\n\s*\n", section_body):
        paragraph = raw.strip()
        if paragraph == "":
            continue
        if len(paragraph) <= budget:
            paragraphs.append(paragraph)
            continue
        paragraphs.extend(
            paragraph[start : start + budget]
            for start in range(0, len(paragraph), budget)
        )
    return paragraphs
