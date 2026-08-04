"""Tests for Obsidian-style YAML list tags in frontmatter."""

from pathlib import Path

from llm_wiki.markdown import (
    ensure_managed_wikilink,
    parse_markdown_file,
    upsert_frontmatter_tags,
)


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


def test_upsert_frontmatter_tags_preserves_unknown_properties() -> None:
    raw = """---
title: Deploy Guide
owner: data-platform
tags: runbook, deployment
aliases:
  - Deploy
---

# Deploy Guide

Body text.
"""

    result = upsert_frontmatter_tags(raw, ("project:evbp-etl", "llm-wiki"))

    assert "owner: data-platform" in result
    assert "aliases:\n  - Deploy" in result
    assert (
        "tags:\n  - runbook\n  - deployment\n  - project:evbp-etl\n  - llm-wiki"
        in result
    )
    assert upsert_frontmatter_tags(result, ("project:evbp-etl", "llm-wiki")) == result


def test_upsert_frontmatter_tags_replaces_block_sequence_in_place() -> None:
    raw = "---\ntitle: Doc\ntags:\n  - one\n  - two\nowner: core\n---\n\nBody.\n"

    result = upsert_frontmatter_tags(raw, ("project:demo",))

    assert "tags:\n  - one\n  - two\n  - project:demo\nowner: core" in result
    assert result.endswith("Body.\n")


def test_upsert_frontmatter_tags_adds_field_when_missing() -> None:
    raw = "---\ntitle: Doc\n---\n\nBody.\n"

    result = upsert_frontmatter_tags(raw, ("project:demo",))

    assert "tags:\n  - project:demo\n---" in result
    assert "title: Doc" in result


def test_upsert_frontmatter_tags_creates_frontmatter_when_absent() -> None:
    raw = "# Bare Note\n\nBody.\n"

    result = upsert_frontmatter_tags(raw, ("project:demo",))

    assert result.startswith("---\n")
    assert "tags:\n  - project:demo" in result
    assert "# Bare Note" in result
    assert upsert_frontmatter_tags(result, ("project:demo",)) == result


def test_managed_wikilink_is_added_once() -> None:
    raw = "---\ntitle: Note\n---\n\n# Note\n\nBody.\n"
    expected = "[[projects/evbp-etl/index]]"

    once = ensure_managed_wikilink(raw, "projects/evbp-etl/index")
    twice = ensure_managed_wikilink(once, "projects/evbp-etl/index")

    assert expected in once
    assert once == twice
    assert once.count("<!-- llm-wiki:project-index -->") == 1


def test_managed_wikilink_block_is_replaced_atomically() -> None:
    raw = (
        "# Note\n\nBody.\n\n"
        "<!-- llm-wiki:project-index -->\n"
        "Related: [[projects/old/index]]\n"
        "<!-- /llm-wiki:project-index -->\n"
    )

    result = ensure_managed_wikilink(raw, "projects/new/index")

    assert "[[projects/new/index]]" in result
    assert "[[projects/old/index]]" not in result
    assert result.count("<!-- llm-wiki:project-index -->") == 1
