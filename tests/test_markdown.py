"""Tests for Markdown and frontmatter parsing at the filesystem boundary."""

from pathlib import Path

import pytest

from llm_wiki.errors import DocumentReadError
from llm_wiki.markdown import parse_markdown_file


def test_parses_title_and_tags_from_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Decision Record\ntags: decision, hooks\n---\n\nBody text.\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.title == "Decision Record"
    assert document.tags == ("decision", "hooks")
    assert document.body == "Body text."


def test_falls_back_to_heading_when_frontmatter_is_absent(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("# Runbook Title\n\nSteps here.\n", encoding="utf-8")

    document = parse_markdown_file(path)

    assert document.title == "Runbook Title"
    assert document.tags == ()


def test_falls_back_to_filename_when_no_heading_exists(tmp_path: Path) -> None:
    path = tmp_path / "hook-event-name.md"
    path.write_text("plain text only\n", encoding="utf-8")

    document = parse_markdown_file(path)

    assert document.title == "Hook Event Name"


def test_treats_unterminated_frontmatter_as_body(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("---\ntitle: Never Closed\n\n# Real Heading\n", encoding="utf-8")

    document = parse_markdown_file(path)

    assert document.title == "Real Heading"
    assert "title: Never Closed" in document.body


def test_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DocumentReadError):
        _ = parse_markdown_file(tmp_path / "absent.md")


def test_rejects_a_directory(tmp_path: Path) -> None:
    with pytest.raises(DocumentReadError):
        _ = parse_markdown_file(tmp_path)


def test_rejects_a_file_that_is_not_valid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "broken.md"
    path.write_bytes(b"---\ntitle: Broken\n---\n\n\xff\xfe\n")

    with pytest.raises(DocumentReadError):
        _ = parse_markdown_file(path)
