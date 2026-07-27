"""Tests for Obsidian-style YAML list tags in frontmatter."""

from pathlib import Path

from llm_wiki.markdown import parse_markdown_file


def test_parses_block_sequence_tags(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Doc\ntags:\n  - architecture\n  - runbook\n---\n\nBody.\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.tags == ("architecture", "runbook")


def test_parses_inline_flow_sequence_tags(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Doc\ntags: [architecture, runbook]\n---\n\nBody.\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.tags == ("architecture", "runbook")


def test_still_parses_legacy_comma_string_tags(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Doc\ntags: architecture, runbook\n---\n\nBody.\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.tags == ("architecture", "runbook")


def test_block_sequence_tags_do_not_leak_into_body(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Doc\ntags:\n  - one\n  - two\n---\n\nReal body.\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.body == "Real body."
    assert "- one" not in document.body


def test_strips_quotes_around_yaml_list_items(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Doc\ntags:\n  - \"hooks\"\n  - 'decisions'\n---\n\nBody.\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.tags == ("hooks", "decisions")
