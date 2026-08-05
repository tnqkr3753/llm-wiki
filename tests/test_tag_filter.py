"""Tests for tag-scoped retrieval (single global wiki, project: namespaces)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.errors import WikiError
from llm_wiki.models import ParsedDocument
from llm_wiki.store import search, upsert_document

runner = CliRunner()


def _index(
    db_path: Path, path: str, title: str, body: str, tags: tuple[str, ...]
) -> None:
    _ = upsert_document(
        db_path,
        ParsedDocument(path=path, title=title, tags=tags, body=body),
    )


def test_search_without_tags_returns_every_match(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/a.md", "Alpha", "shared body", ("project:foo",))
    _index(db_path, "/b.md", "Beta", "shared body", ("project:bar",))

    assert len(search(db_path, "shared", limit=10)) == 2


def test_search_filters_to_a_single_tag(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/a.md", "Alpha", "shared body", ("project:foo",))
    _index(db_path, "/b.md", "Beta", "shared body", ("project:bar",))

    results = search(db_path, "shared", limit=10, tags=("project:foo",))

    assert [r.title for r in results] == ["Alpha"]


def test_multiple_tags_require_all_of_them(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/a.md", "Alpha", "shared body", ("project:foo", "runbook"))
    _index(db_path, "/b.md", "Beta", "shared body", ("project:foo",))

    results = search(db_path, "shared", limit=10, tags=("project:foo", "runbook"))

    assert [r.title for r in results] == ["Alpha"]


def test_tag_match_is_exact_not_substring(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/a.md", "Alpha", "shared body", ("project:foo",))
    _index(db_path, "/b.md", "Beta", "shared body", ("project:foobar",))

    results = search(db_path, "shared", limit=10, tags=("project:foo",))

    assert [r.title for r in results] == ["Alpha"]


def test_tag_filter_does_not_lose_matches_beyond_limit(tmp_path: Path) -> None:
    """A tagged doc ranked below many untagged ones must still surface."""
    db_path = tmp_path / "wiki.db"
    for i in range(15):
        _index(db_path, f"/noise{i}.md", f"Noise {i}", "shared body", ("project:bar",))
    _index(db_path, "/wanted.md", "Wanted", "shared body", ("project:foo",))

    results = search(db_path, "shared", limit=5, tags=("project:foo",))

    assert [r.title for r in results] == ["Wanted"]


def test_search_command_accepts_repeated_tag_option(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/a.md", "Alpha", "shared body", ("project:foo",))
    _index(db_path, "/b.md", "Beta", "shared body", ("project:bar",))

    result = runner.invoke(
        app, ["search", "shared", "--db", str(db_path), "--tag", "project:foo"]
    )

    assert result.exit_code == 0
    assert "Alpha" in result.output
    assert "Beta" not in result.output


def test_ask_context_command_filters_by_tag(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/a.md", "Alpha", "grounded body", ("project:foo",))
    _index(db_path, "/b.md", "Beta", "grounded body", ("project:bar",))

    result = runner.invoke(
        app, ["ask-context", "grounded", "--db", str(db_path), "--tag", "project:bar"]
    )

    assert result.exit_code == 0
    assert "Beta" in result.output
    assert "Alpha" not in result.output


def test_project_scope_includes_common_and_selected_project(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/common.md", "Common", "shared body", ("reference",))
    _index(db_path, "/foo.md", "Foo", "shared body", ("project:foo",))
    _index(db_path, "/bar.md", "Bar", "shared body", ("project:bar",))

    results = search(db_path, "shared", limit=10, project="foo")

    assert {item.title for item in results} == {"Common", "Foo"}


def test_project_scope_and_tag_filter_both_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/common.md", "Common", "body", ("runbook",))
    _index(db_path, "/foo.md", "Foo", "body", ("project:foo", "decision"))

    results = search(db_path, "body", limit=10, project="foo", tags=("runbook",))

    assert [item.title for item in results] == ["Common"]


def test_project_scope_accepts_full_project_tag(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/foo.md", "Foo", "body", ("project:foo",))
    _index(db_path, "/bar.md", "Bar", "body", ("project:bar",))

    results = search(db_path, "body", limit=10, project="project:foo")

    assert [item.title for item in results] == ["Foo"]


def test_project_scope_rejects_invalid_slug(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/foo.md", "Foo", "body", ("project:foo",))

    with pytest.raises(WikiError):
        _ = search(db_path, "body", limit=10, project="not a slug")


def test_project_scope_survives_low_ranking(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    for index in range(30):
        _index(
            db_path,
            f"/other-{index}.md",
            f"Other {index}",
            "shared body shared body shared body",
            ("project:other",),
        )
    _index(db_path, "/foo.md", "Foo", "shared body", ("project:foo",))

    results = search(db_path, "shared", limit=5, project="foo")

    assert [item.title for item in results] == ["Foo"]


def test_search_cli_supports_project_option(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/common.md", "Common CLI", "cli body", ("reference",))
    _index(db_path, "/foo.md", "Foo CLI", "cli body", ("project:foo",))
    _index(db_path, "/bar.md", "Bar CLI", "cli body", ("project:bar",))

    result = runner.invoke(
        app,
        ["search", "cli", "--db", str(db_path), "--project", "foo"],
    )

    assert result.exit_code == 0
    assert "Common CLI" in result.output
    assert "Foo CLI" in result.output
    assert "Bar CLI" not in result.output


def test_ask_context_cli_supports_project_option(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/common.md", "Common Ctx", "context body", ("reference",))
    _index(db_path, "/foo.md", "Foo Ctx", "context body", ("project:foo",))
    _index(db_path, "/bar.md", "Bar Ctx", "context body", ("project:bar",))

    result = runner.invoke(
        app,
        ["ask-context", "context", "--db", str(db_path), "--project", "foo"],
    )

    assert result.exit_code == 0
    assert "Common Ctx" in result.output
    assert "Foo Ctx" in result.output
    assert "Bar Ctx" not in result.output


def test_draft_documents_rank_below_official_ones(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(
        db_path,
        "/draft.md",
        "Draft Note",
        "shared body shared shared context",
        ("project:foo", "draft"),
    )
    _index(db_path, "/official.md", "Official Note", "shared body", ("project:foo",))

    results = search(db_path, "shared", limit=10, project="foo")

    assert {item.title for item in results} == {"Draft Note", "Official Note"}
    assert results[0].title == "Official Note"


def test_draft_only_results_are_still_returned(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    _index(db_path, "/draft.md", "Draft Only", "unique body", ("draft",))

    results = search(db_path, "unique", limit=10)

    assert [item.title for item in results] == ["Draft Only"]
