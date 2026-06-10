"""Markdown and frontmatter parsing."""

from pathlib import Path

from llm_wiki.errors import DocumentReadError
from llm_wiki.models import ParsedDocument

FRONTMATTER_DELIMITER = "---"
MIN_FRONTMATTER_LINES = 2


def parse_markdown_file(path: Path) -> ParsedDocument:
    """Read and parse a Markdown file into a typed document."""
    if not path.exists():
        raise DocumentReadError.missing(path)
    if not path.is_file():
        raise DocumentReadError.not_file(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentReadError.unreadable(path) from exc

    title, tags, body = _split_frontmatter(raw, path)
    return ParsedDocument(path=str(path), title=title, tags=tags, body=body)


def _split_frontmatter(raw: str, path: Path) -> tuple[str, tuple[str, ...], str]:
    lines = raw.splitlines()
    has_frontmatter = (
        len(lines) >= MIN_FRONTMATTER_LINES
        and lines[0].strip() == FRONTMATTER_DELIMITER
    )
    if has_frontmatter:
        return _parse_frontmatter(lines, path)

    title = _fallback_title(path, raw)
    return title, (), raw.strip()


def _parse_frontmatter(
    lines: list[str],
    path: Path,
) -> tuple[str, tuple[str, ...], str]:
    closing_index = _find_closing_delimiter(lines)
    if closing_index is None:
        title = _fallback_title(path, "\n".join(lines))
        return title, (), "\n".join(lines).strip()

    title = ""
    tags: tuple[str, ...] = ()
    for line in lines[1:closing_index]:
        key, separator, value = line.partition(":")
        if separator == "":
            continue
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key == "title":
            title = normalized_value
        if normalized_key == "tags":
            tags = tuple(
                tag.strip() for tag in normalized_value.split(",") if tag.strip() != ""
            )

    body = "\n".join(lines[closing_index + 1 :]).strip()
    if title == "":
        title = _fallback_title(path, body)
    return title, tags, body


def _find_closing_delimiter(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            return index
    return None


def _fallback_title(path: Path, body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return path.stem.replace("-", " ").replace("_", " ").title()
