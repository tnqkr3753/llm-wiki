"""Markdown and frontmatter parsing."""

import re
from collections.abc import Sequence
from pathlib import Path

from llm_wiki.errors import DocumentReadError
from llm_wiki.models import ParsedDocument

FRONTMATTER_DELIMITER = "---"
MIN_FRONTMATTER_LINES = 2
WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]]+?)\]\]")
FENCED_CODE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
PROJECT_INDEX_BLOCK = "project-index"


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
    the target names a document, matching Obsidian's own resolution. Links inside
    inline code spans or fenced code blocks are ignored — Obsidian does not treat
    those as edges either, so a page documenting `[[wikilink]]` syntax does not
    accidentally link to the pages it names as examples.
    """
    scrubbed = FENCED_CODE_PATTERN.sub(" ", body)
    scrubbed = INLINE_CODE_PATTERN.sub(" ", scrubbed)
    targets: list[str] = []
    for match in WIKILINK_PATTERN.finditer(scrubbed):
        raw_target = match.group(1)
        target = raw_target.split("|", 1)[0].split("#", 1)[0].strip()
        if target != "" and target not in targets:
            targets.append(target)
    return tuple(targets)


def upsert_frontmatter_tags(raw: str, required: Sequence[str]) -> str:
    """Rewrite only the frontmatter `tags` field as a YAML block list.

    Every other frontmatter line and the body stay byte-for-byte identical,
    except that a missing final newline is normalized.
    """
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]

    has_frontmatter = (
        len(lines) >= MIN_FRONTMATTER_LINES
        and lines[0].strip() == FRONTMATTER_DELIMITER
    )
    closing_index = _find_closing_delimiter(lines) if has_frontmatter else None
    if closing_index is None:
        return _prepend_frontmatter(lines, required)

    span = _find_tags_span(lines, closing_index)
    if span is None:
        current_tags: tuple[str, ...] = ()
        insert_at = closing_index
        remove_until = closing_index
    else:
        start, end = span
        inline_value = lines[start].partition(":")[2].strip()
        current_tags = _parse_tags(inline_value, lines, start + 1, closing_index)
        insert_at = start
        remove_until = end

    rendered = _render_tags_block(current_tags, required)
    updated = lines[:insert_at] + rendered + lines[remove_until:]
    return "\n".join(updated) + "\n"


def ensure_managed_wikilink(raw: str, target: str) -> str:
    """Insert or replace the managed project-index backlink block."""
    content = f"Related: [[{target}]]"
    return replace_managed_block(raw, PROJECT_INDEX_BLOCK, (content,))


def replace_managed_block(raw: str, name: str, content_lines: Sequence[str]) -> str:
    """Insert or atomically replace a `<!-- llm-wiki:{name} -->` block."""
    start_marker = f"<!-- llm-wiki:{name} -->"
    end_marker = f"<!-- /llm-wiki:{name} -->"
    block = "\n".join((start_marker, *content_lines, end_marker))

    normalized = raw if raw.endswith("\n") else f"{raw}\n"
    start = normalized.find(start_marker)
    end = normalized.find(end_marker)
    if start != -1 and end != -1 and end > start:
        tail = normalized[end + len(end_marker) :]
        return f"{normalized[:start]}{block}{tail}"

    separator = "" if normalized.endswith("\n\n") else "\n"
    return f"{normalized}{separator}{block}\n"


def _find_tags_span(lines: list[str], closing_index: int) -> tuple[int, int] | None:
    for index in range(1, closing_index):
        key, separator, value = lines[index].partition(":")
        if separator == "" or key.strip().lower() != "tags":
            continue
        end = index + 1
        if value.strip() == "":
            while end < closing_index and lines[end].strip().startswith("- "):
                end += 1
        return index, end
    return None


def _render_tags_block(
    current_tags: Sequence[str], required: Sequence[str]
) -> list[str]:
    merged: list[str] = []
    for tag in (*current_tags, *required):
        if tag not in merged:
            merged.append(tag)
    return ["tags:", *[f"  - {tag}" for tag in merged]]


def _prepend_frontmatter(lines: list[str], required: Sequence[str]) -> str:
    heading_title = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            heading_title = stripped.removeprefix("# ").strip()
            break

    frontmatter = [FRONTMATTER_DELIMITER]
    if heading_title != "":
        frontmatter.append(f"title: {heading_title}")
    frontmatter.extend(_render_tags_block((), required))
    frontmatter.append(FRONTMATTER_DELIMITER)
    return "\n".join([*frontmatter, "", *lines]) + "\n"


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
