"""Tests for the dry-run-first global vault materializer and auditor."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_wiki.cli import app
from llm_wiki.errors import VaultError
from llm_wiki.global_vault import (
    ProjectSource,
    apply_global_vault,
    audit_global_vault,
    plan_global_vault,
)
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.store import reindex_directory, upsert_document

runner = CliRunner()


def _make_source(tmp_path: Path, slug: str, files: dict[str, str]) -> ProjectSource:
    root = tmp_path / "sources" / slug / "docs"
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(body, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return ProjectSource(slug=slug, docs_root=root)


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True, exist_ok=True)
    return home


DOC = "---\ntitle: A\ntags: decision\n---\n\n# A\n\nBody.\n"


def test_plan_maps_relative_paths_into_project_namespace(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})

    plan = plan_global_vault(home, [source])

    targets = {entry.target for entry in plan.entries}
    assert home / "docs" / "projects" / "alpha" / "decisions" / "a.md" in targets
    assert plan.conflicts == ()


def test_plan_makes_index_the_project_hub(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(
        tmp_path,
        "alpha",
        {"index.md": "# Alpha\n", "decisions/a.md": DOC},
    )

    plan = plan_global_vault(home, [source])

    hub = home / "docs" / "projects" / "alpha" / "index.md"
    assert hub in {entry.target for entry in plan.entries}


def test_dry_run_creates_no_files(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    before = sorted(str(p) for p in home.rglob("*"))

    _ = plan_global_vault(home, [source])

    assert sorted(str(p) for p in home.rglob("*")) == before


def test_apply_then_replan_is_unchanged(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(
        tmp_path,
        "alpha",
        {"index.md": "# Alpha\n", "decisions/a.md": DOC},
    )

    _ = apply_global_vault(plan_global_vault(home, [source]))
    replan = plan_global_vault(home, [source])

    actions = {entry.action for entry in replan.entries}
    assert actions == {"unchanged"}
    assert replan.conflicts == ()


def test_repeated_apply_is_idempotent_and_blocks_duplicates(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(
        tmp_path,
        "alpha",
        {"index.md": "# Alpha\n", "decisions/a.md": DOC},
    )

    _ = apply_global_vault(plan_global_vault(home, [source]))
    first = (home / "docs" / "projects" / "alpha" / "index.md").read_text("utf-8")
    _ = apply_global_vault(plan_global_vault(home, [source]))
    second = (home / "docs" / "projects" / "alpha" / "index.md").read_text("utf-8")

    assert first == second
    assert first.count("<!-- llm-wiki:notes -->") == 1
    global_index = (home / "docs" / "index.md").read_text("utf-8")
    assert global_index.count("<!-- llm-wiki:projects -->") == 1


def test_preexisting_unmanaged_target_is_conflict(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    conflict_target = home / "docs" / "projects" / "alpha" / "decisions" / "a.md"
    conflict_target.parent.mkdir(parents=True, exist_ok=True)
    _ = conflict_target.write_text(DOC, encoding="utf-8")

    plan = plan_global_vault(home, [source])

    assert conflict_target in {entry.target for entry in plan.conflicts}
    with pytest.raises(VaultError):
        _ = apply_global_vault(plan)
    assert conflict_target.read_text("utf-8") == DOC


def test_symlink_escaping_source_root_is_skipped(tmp_path: Path) -> None:
    home = _home(tmp_path)
    outside = tmp_path / "outside.md"
    _ = outside.write_text("# Outside\n", encoding="utf-8")
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    (source.docs_root / "escape.md").symlink_to(outside)

    plan = plan_global_vault(home, [source])

    assert source.docs_root / "escape.md" in plan.skipped
    assert not any(
        entry.source == source.docs_root / "escape.md" for entry in plan.entries
    )


def test_same_relative_filename_does_not_collide_across_projects(
    tmp_path: Path,
) -> None:
    home = _home(tmp_path)
    alpha = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    beta = _make_source(tmp_path, "beta", {"decisions/a.md": DOC})

    plan = plan_global_vault(home, [alpha, beta])

    targets = [entry.target for entry in plan.entries]
    assert len(targets) == len(set(targets))
    assert plan.conflicts == ()


def test_duplicate_or_invalid_slug_is_rejected(tmp_path: Path) -> None:
    home = _home(tmp_path)
    alpha = _make_source(tmp_path, "alpha", {"a.md": DOC})

    with pytest.raises(VaultError):
        _ = plan_global_vault(home, [alpha, alpha])
    with pytest.raises(VaultError):
        _ = plan_global_vault(
            home, [ProjectSource(slug="Bad Slug", docs_root=alpha.docs_root)]
        )


def test_hub_links_every_note_and_global_index_links_every_hub(
    tmp_path: Path,
) -> None:
    home = _home(tmp_path)
    alpha = _make_source(
        tmp_path,
        "alpha",
        {"index.md": "# Alpha\n", "decisions/a.md": DOC, "runbooks/r.md": DOC},
    )
    beta = _make_source(tmp_path, "beta", {"notes/b.md": DOC})

    _ = apply_global_vault(plan_global_vault(home, [alpha, beta]))

    alpha_hub = (home / "docs" / "projects" / "alpha" / "index.md").read_text("utf-8")
    beta_hub = (home / "docs" / "projects" / "beta" / "index.md").read_text("utf-8")
    global_index = (home / "docs" / "index.md").read_text("utf-8")
    assert "[[projects/alpha/decisions/a]]" in alpha_hub
    assert "[[projects/alpha/runbooks/r]]" in alpha_hub
    assert "[[projects/beta/notes/b]]" in beta_hub
    assert "[[projects/alpha/index]]" in global_index
    assert "[[projects/beta/index]]" in global_index


def test_notes_receive_project_tag_and_hub_backlink(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})

    _ = apply_global_vault(plan_global_vault(home, [source]))

    note = (home / "docs" / "projects" / "alpha" / "decisions" / "a.md").read_text(
        "utf-8"
    )
    assert "  - project:alpha" in note
    assert "Related: [[projects/alpha/index]]" in note
    assert "  - decision" in note


def test_apply_preserves_source_files_and_writes_manifest(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    source_file = source.docs_root / "decisions" / "a.md"
    before = source_file.read_bytes()

    manifest_path = apply_global_vault(plan_global_vault(home, [source]))

    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert source_file.read_bytes() == before
    assert manifest["version"] == 1
    assert manifest["status"] == "applied"
    assert manifest["sources"][0]["slug"] == "alpha"
    entry = manifest["entries"][0]
    assert {"source", "target", "source_sha256", "rendered_sha256", "action"} <= set(
        entry
    )
    assert manifest["conflicts"] == []


def test_interrupted_staging_content_is_not_managed_output(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    staging = home / ".vault-staging"
    (staging / "docs" / "projects" / "alpha").mkdir(parents=True)
    _ = (staging / "docs" / "projects" / "alpha" / "junk.md").write_text(
        "# Junk\n", encoding="utf-8"
    )

    _ = apply_global_vault(plan_global_vault(home, [source]))

    assert not (home / "docs" / "projects" / "alpha" / "junk.md").exists()
    assert not staging.exists()


def test_native_global_docs_outside_projects_are_preserved(tmp_path: Path) -> None:
    home = _home(tmp_path)
    native = home / "docs" / "references" / "native.md"
    native.parent.mkdir(parents=True)
    _ = native.write_text("# Native\n", encoding="utf-8")
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})

    _ = apply_global_vault(plan_global_vault(home, [source]))

    assert native.read_text("utf-8") == "# Native\n"


def test_audit_reports_clean_vault(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(
        tmp_path,
        "alpha",
        {"index.md": "# Alpha\n", "decisions/a.md": DOC},
    )
    _ = apply_global_vault(plan_global_vault(home, [source]))
    db_path = home / "wiki.db"
    _ = reindex_directory(db_path, home / "docs")

    audit = audit_global_vault(home, db_path)

    assert audit.markdown_files == audit.indexed_documents
    assert audit.external_index_paths == ()
    assert audit.orphan_paths == ()
    assert audit.unresolved_targets == ()
    assert audit.resolved_edges > 0


def test_audit_names_external_paths_and_orphans(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(
        tmp_path,
        "alpha",
        {"index.md": "# Alpha\n", "decisions/a.md": DOC},
    )
    _ = apply_global_vault(plan_global_vault(home, [source]))
    db_path = home / "wiki.db"
    _ = reindex_directory(db_path, home / "docs")

    external = tmp_path / "external.md"
    _ = external.write_text("# External\n", encoding="utf-8")
    _ = upsert_document(db_path, parse_markdown_file(external))

    orphan = home / "docs" / "orphan.md"
    _ = orphan.write_text(
        "---\ntitle: Orphan\n---\n\nNo [[missing-note]] resolves here.\n",
        encoding="utf-8",
    )
    _ = upsert_document(db_path, parse_markdown_file(orphan))

    audit = audit_global_vault(home, db_path)

    assert external.resolve() in audit.external_index_paths
    assert orphan.resolve() in audit.orphan_paths
    assert "missing-note" in audit.unresolved_targets


def test_vault_import_cli_dry_run_and_apply(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})

    dry = runner.invoke(
        app,
        [
            "vault",
            "import",
            "--source",
            f"alpha={source.docs_root}",
            "--home",
            str(home),
        ],
    )
    assert dry.exit_code == 0
    assert (
        "create=1" in dry.output.replace(" ", "").replace(":", "=")
        or "create" in dry.output
    )
    assert not (home / "docs" / "projects").exists()

    applied = runner.invoke(
        app,
        [
            "vault",
            "import",
            "--source",
            f"alpha={source.docs_root}",
            "--home",
            str(home),
            "--apply",
        ],
    )
    assert applied.exit_code == 0
    assert (home / "docs" / "projects" / "alpha" / "decisions" / "a.md").is_file()


def test_vault_import_cli_apply_exits_nonzero_on_conflict(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    conflict_target = home / "docs" / "projects" / "alpha" / "decisions" / "a.md"
    conflict_target.parent.mkdir(parents=True, exist_ok=True)
    _ = conflict_target.write_text("user content\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "vault",
            "import",
            "--source",
            f"alpha={source.docs_root}",
            "--home",
            str(home),
            "--apply",
        ],
    )

    assert result.exit_code == 1
    assert conflict_target.read_text("utf-8") == "user content\n"


def test_vault_import_cli_rejects_bad_source_spec(tmp_path: Path) -> None:
    home = _home(tmp_path)

    result = runner.invoke(
        app,
        ["vault", "import", "--source", "no-equals-here", "--home", str(home)],
    )

    assert result.exit_code == 1


def test_vault_audit_cli_reports_counts(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    _ = apply_global_vault(plan_global_vault(home, [source]))
    db_path = home / "wiki.db"
    _ = reindex_directory(db_path, home / "docs")

    result = runner.invoke(
        app,
        ["vault", "audit", "--home", str(home), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "markdown_files" in result.output
    assert "external_index_paths" in result.output


def test_locally_modified_managed_target_blocks_apply(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    _ = apply_global_vault(plan_global_vault(home, [source]))
    managed = home / "docs" / "projects" / "alpha" / "decisions" / "a.md"
    edited = managed.read_text("utf-8") + "\nVault-side manual edit.\n"
    _ = managed.write_text(edited, encoding="utf-8")

    replan = plan_global_vault(home, [source])

    assert managed in {entry.target for entry in replan.conflicts}
    with pytest.raises(VaultError):
        _ = apply_global_vault(replan)
    assert managed.read_text("utf-8") == edited


def test_source_update_of_pristine_target_is_update(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    _ = apply_global_vault(plan_global_vault(home, [source]))
    source_file = source.docs_root / "decisions" / "a.md"
    _ = source_file.write_text(
        DOC.replace("Body.", "Updated source body."), encoding="utf-8"
    )

    replan = plan_global_vault(home, [source])
    managed = home / "docs" / "projects" / "alpha" / "decisions" / "a.md"
    actions = {entry.target: entry.action for entry in replan.entries}

    assert actions[managed] == "update"
    assert replan.conflicts == ()
    _ = apply_global_vault(replan)
    assert "Updated source body." in managed.read_text("utf-8")


def test_hub_and_index_blocks_keep_foreign_physical_notes(tmp_path: Path) -> None:
    home = _home(tmp_path)
    source = _make_source(tmp_path, "alpha", {"decisions/a.md": DOC})
    _ = apply_global_vault(plan_global_vault(home, [source]))

    foreign_note = home / "docs" / "projects" / "alpha" / "notes" / "from-mac.md"
    foreign_note.parent.mkdir(parents=True)
    _ = foreign_note.write_text("---\ntitle: Foreign\n---\n\nBody.\n", encoding="utf-8")
    foreign_hub = home / "docs" / "projects" / "beta" / "index.md"
    foreign_hub.parent.mkdir(parents=True)
    _ = foreign_hub.write_text("---\ntitle: Beta\n---\n\n# Beta\n", encoding="utf-8")

    _ = apply_global_vault(plan_global_vault(home, [source]))

    alpha_hub = (home / "docs" / "projects" / "alpha" / "index.md").read_text("utf-8")
    global_index = (home / "docs" / "index.md").read_text("utf-8")
    assert "[[projects/alpha/notes/from-mac]]" in alpha_hub
    assert "[[projects/alpha/decisions/a]]" in alpha_hub
    assert "[[projects/beta/index]]" in global_index
    assert "[[projects/alpha/index]]" in global_index
