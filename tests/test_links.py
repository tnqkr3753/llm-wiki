"""Tests for wikilink parsing and the document-link graph."""

from pathlib import Path

from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.markdown import parse_markdown_file, parse_wikilinks
from llm_wiki.models import ParsedDocument
from llm_wiki.store import backlinks, outgoing_links, upsert_document

runner = CliRunner()


def _write_doc(path: Path, title: str, body: str, tags: str = "tags: test") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n{tags}\n---\n\n{body}\n", encoding="utf-8")


def test_parse_wikilinks_extracts_bare_targets() -> None:
    assert parse_wikilinks("See [[manual]] and [[decisions/hook-invariant]].") == (
        "manual",
        "decisions/hook-invariant",
    )


def test_parse_wikilinks_uses_target_not_alias() -> None:
    assert parse_wikilinks("Read [[manual|the manual]].") == ("manual",)


def test_parse_wikilinks_strips_heading_anchor() -> None:
    assert parse_wikilinks("Jump to [[manual#Setup]].") == ("manual",)


def test_parse_wikilinks_deduplicates_preserving_order() -> None:
    assert parse_wikilinks("[[b]] [[a]] [[b]]") == ("b", "a")


def test_parse_wikilinks_ignores_empty_targets() -> None:
    assert parse_wikilinks("noise [[]] [[  ]] end") == ()


def test_parsed_document_exposes_links(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: Hub\ntags: index\n---\n\nSee [[alpha]] and [[beta]].\n",
        encoding="utf-8",
    )

    document = parse_markdown_file(path)

    assert document.links == ("alpha", "beta")


def test_outgoing_links_resolve_to_indexed_documents(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    hub = tmp_path / "docs" / "index.md"
    alpha = tmp_path / "docs" / "alpha.md"
    _write_doc(hub, "Index", "Start at [[alpha]].")
    _write_doc(alpha, "Alpha", "Leaf content.")
    hub_id = upsert_document(db_path, parse_markdown_file(hub))
    alpha_id = upsert_document(db_path, parse_markdown_file(alpha))

    links = outgoing_links(db_path, hub_id)

    assert [(link.id, link.title) for link in links] == [(alpha_id, "Alpha")]


def test_outgoing_links_resolve_nested_relative_targets(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    hub = tmp_path / "docs" / "index.md"
    nested = tmp_path / "docs" / "decisions" / "rule.md"
    _write_doc(hub, "Index", "See [[decisions/rule]].")
    _write_doc(nested, "Rule", "A decision.")
    hub_id = upsert_document(db_path, parse_markdown_file(hub))
    _ = upsert_document(db_path, parse_markdown_file(nested))

    titles = [link.title for link in outgoing_links(db_path, hub_id)]

    assert titles == ["Rule"]


def test_backlinks_report_documents_that_link_here(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    hub = tmp_path / "docs" / "index.md"
    alpha = tmp_path / "docs" / "alpha.md"
    _write_doc(hub, "Index", "Start at [[alpha]].")
    _write_doc(alpha, "Alpha", "Leaf content.")
    hub_id = upsert_document(db_path, parse_markdown_file(hub))
    alpha_id = upsert_document(db_path, parse_markdown_file(alpha))

    incoming = backlinks(db_path, alpha_id)

    assert [(link.id, link.title) for link in incoming] == [(hub_id, "Index")]


def test_links_are_replaced_when_a_document_is_reindexed(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    hub = tmp_path / "docs" / "index.md"
    alpha = tmp_path / "docs" / "alpha.md"
    _write_doc(hub, "Index", "Start at [[alpha]].")
    _write_doc(alpha, "Alpha", "Leaf content.")
    hub_id = upsert_document(db_path, parse_markdown_file(hub))
    alpha_id = upsert_document(db_path, parse_markdown_file(alpha))

    _write_doc(hub, "Index", "Now empty.")
    _ = upsert_document(db_path, parse_markdown_file(hub))

    assert outgoing_links(db_path, hub_id) == ()
    assert backlinks(db_path, alpha_id) == ()


def test_unresolved_link_targets_are_omitted(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    hub = tmp_path / "docs" / "index.md"
    _write_doc(hub, "Index", "Dangling [[does-not-exist]].")
    hub_id = upsert_document(db_path, parse_markdown_file(hub))

    assert outgoing_links(db_path, hub_id) == ()


def test_links_command_shows_outgoing_and_incoming(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    hub = tmp_path / "docs" / "index.md"
    alpha = tmp_path / "docs" / "alpha.md"
    _write_doc(hub, "Index", "Start at [[alpha]].")
    _write_doc(alpha, "Alpha", "Leaf content.")
    hub_id = int(upsert_document(db_path, parse_markdown_file(hub)))
    _ = upsert_document(db_path, parse_markdown_file(alpha))

    result = runner.invoke(app, ["links", str(hub_id), "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Alpha" in result.output


def test_upsert_document_without_links_keeps_empty_graph(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    document = ParsedDocument(
        path=str(tmp_path / "a.md"), title="A", tags=("t",), body="no links"
    )
    document_id = upsert_document(db_path, document)

    assert outgoing_links(db_path, document_id) == ()
