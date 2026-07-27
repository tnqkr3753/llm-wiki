"""Markdown and frontmatter parsing."""

import re
from pathlib import Path

from llm_wiki.errors import DocumentReadError
from llm_wiki.models import ParsedDocument

FRONTMATTER_DELIMITER = "---"
MIN_FRONTMATTER_LINES = 2
WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]]+?)\]\]")


def parse_markdown_file(path: Path) -> ParsedDocument:
    """Read and parse a Markdown file into a typed document."""
    if not path.exists():
        raise DocumentReadError.missing(path)
    if not path.is_file():
        raise DocumentReadError.not_file(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DocumentReadError.unreadable(path) from exc

    title, tags, body = _split_frontmatter(raw, path)
    return ParsedDocument(
        path=str(path),
        title=title,
        tags=tags,
        body=body,
        links=parse_wikilinks(body),
    )


def parse_wikilinks(body: str) -> tuple[str, ...]:
    """Extract deduplicated `[[target]]` wikilink targets in first-seen order.

    Alias (`target|alias`) and heading anchors (`target#Section`) are dropped so
    the target names a document, matching Obsidian's own resolution.
    """
    targets: list[str] = []
    for match in WIKILINK_PATTERN.finditer(body):
        raw_target = match.group(1)
        target = raw_target.split("|", 1)[0].split("#", 1)[0].strip()
        if target != "" and target not in targets:
            targets.append(target)
    return tuple(targets)


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
    for index in range(1, closing_index):
        key, separator, value = lines[index].partition(":")
        if separator == "":
            continue
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key == "title":
            title = normalized_value
        if normalized_key == "tags":
            tags = _parse_tags(normalized_value, lines, index + 1, closing_index)

    body = "\n".join(lines[closing_index + 1 :]).strip()
    if title == "":
        title = _fallback_title(path, body)
    return title, tags, body


def _parse_tags(
    inline_value: str,
    lines: list[str],
    next_index: int,
    closing_index: int,
) -> tuple[str, ...]:
    """Parse tags from a comma string, an inline `[a, b]`, or a block sequence."""
    if inline_value == "":
        return _parse_block_sequence(lines, next_index, closing_index)
    unwrapped = inline_value.removeprefix("[").removesuffix("]")
    return tuple(
        _strip_tag_quotes(tag)
        for tag in unwrapped.split(",")
        if _strip_tag_quotes(tag) != ""
    )


def _parse_block_sequence(
    lines: list[str],
    next_index: int,
    closing_index: int,
) -> tuple[str, ...]:
    items: list[str] = []
    for index in range(next_index, closing_index):
        stripped = lines[index].strip()
        if not stripped.startswith("- "):
            break
        item = _strip_tag_quotes(stripped.removeprefix("- "))
        if item != "":
            items.append(item)
    return tuple(items)


def _strip_tag_quotes(tag: str) -> str:
    stripped = tag.strip()
    is_quoted = (
        len(stripped) >= MIN_FRONTMATTER_LINES
        and stripped[0] in "\"'"
        and stripped[-1] == stripped[0]
    )
    if is_quoted:
        return stripped[1:-1].strip()
    return stripped


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
