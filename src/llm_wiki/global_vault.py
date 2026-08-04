"""Dry-run-first materialization of project docs into one global vault."""

import hashlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from llm_wiki.config import PROJECT_SLUG_PATTERN
from llm_wiki.errors import VaultError
from llm_wiki.markdown import (
    ensure_managed_wikilink,
    replace_managed_block,
    upsert_frontmatter_tags,
)
from llm_wiki.store import iter_markdown_files, link_graph

MANIFEST_VERSION = 1
MANIFEST_DIR = "migrations"
STAGING_DIR = ".vault-staging"
PROJECTS_DIR = "projects"
NOTES_BLOCK = "notes"
PROJECTS_BLOCK = "projects"

type VaultAction = Literal["create", "update", "unchanged", "conflict"]

HUB_TEMPLATE = """---
title: {title}
---

# {title}
"""

GLOBAL_INDEX_TEMPLATE = """---
title: LLM Wiki Index
---

# LLM Wiki Index
"""


@dataclass(frozen=True, slots=True)
class ProjectSource:
    """One approved project docs root to import."""

    slug: str
    docs_root: Path


@dataclass(frozen=True, slots=True)
class VaultEntry:
    """One planned file materialization into the global vault."""

    source: Path
    target: Path
    source_sha256: str
    rendered_sha256: str
    action: VaultAction
    rendered: str = ""
    conflict_reason: str = ""


@dataclass(frozen=True, slots=True)
class VaultPlan:
    """A deterministic, side-effect-free vault materialization plan."""

    home: Path
    sources: tuple[ProjectSource, ...]
    entries: tuple[VaultEntry, ...]
    skipped: tuple[Path, ...]
    conflicts: tuple[VaultEntry, ...]


@dataclass(frozen=True, slots=True)
class VaultAudit:
    """Comparison of physical vault files against the retrieval index."""

    markdown_files: int
    indexed_documents: int
    resolved_edges: int
    orphan_paths: tuple[Path, ...]
    unresolved_targets: tuple[str, ...]
    external_index_paths: tuple[Path, ...]


def plan_global_vault(home: Path, sources: Sequence[ProjectSource]) -> VaultPlan:
    """Plan namespaced copies without changing source or destination files."""
    resolved_home = home.expanduser().resolve()
    ordered = _validated_sources(sources)
    owned_state = _owned_state(resolved_home)

    entries: list[VaultEntry] = []
    skipped: list[Path] = []
    hub_links: list[str] = []
    for source in ordered:
        source_entries, source_skipped = _plan_source(resolved_home, source)
        entries.extend(source_entries)
        skipped.extend(source_skipped)
        hub_links.append(f"{PROJECTS_DIR}/{source.slug}/index")

    entries.append(_plan_global_index(resolved_home, hub_links))

    finalized = tuple(
        _with_action(entry, owned_state) for entry in sorted(entries, key=_target_key)
    )
    conflicts = tuple(entry for entry in finalized if entry.action == "conflict")
    return VaultPlan(
        home=resolved_home,
        sources=tuple(ordered),
        entries=finalized,
        skipped=tuple(sorted(skipped)),
        conflicts=conflicts,
    )


def apply_global_vault(plan: VaultPlan) -> Path:
    """Apply a conflict-free plan and return the JSON manifest path."""
    if plan.conflicts:
        raise VaultError.conflicts_block_apply(len(plan.conflicts))

    staging = plan.home / STAGING_DIR
    if staging.exists():
        shutil.rmtree(staging)

    pending = [entry for entry in plan.entries if entry.action in ("create", "update")]
    for entry in pending:
        staged = staging / entry.target.relative_to(plan.home)
        staged.parent.mkdir(parents=True, exist_ok=True)
        _ = staged.write_text(entry.rendered, encoding="utf-8")

    manifest_path = _write_manifest(plan, status="planned")
    for entry in pending:
        staged = staging / entry.target.relative_to(plan.home)
        entry.target.parent.mkdir(parents=True, exist_ok=True)
        _ = staged.replace(entry.target)

    _ = _write_manifest(plan, status="applied", manifest_path=manifest_path)
    if staging.exists():
        shutil.rmtree(staging)
    return manifest_path


def audit_global_vault(home: Path, db_path: Path) -> VaultAudit:
    """Compare physical Markdown, indexed paths, resolved graph edges, orphans."""
    docs_root = (home.expanduser() / "docs").resolve()
    physical = list(iter_markdown_files(docs_root))
    documents, resolved_edges, unresolved_targets = link_graph(db_path)

    external = tuple(
        sorted(
            Path(document.path)
            for document in documents
            if not Path(document.path).is_relative_to(docs_root)
        )
    )

    linked_ids = {source for source, _ in resolved_edges} | {
        target for _, target in resolved_edges
    }
    orphans = tuple(
        sorted(
            Path(document.path)
            for document in documents
            if Path(document.path).is_relative_to(docs_root)
            and int(document.id) not in linked_ids
        )
    )
    return VaultAudit(
        markdown_files=len(physical),
        indexed_documents=len(documents),
        resolved_edges=len(resolved_edges),
        orphan_paths=orphans,
        unresolved_targets=tuple(sorted(unresolved_targets)),
        external_index_paths=external,
    )


def parse_source_mapping(spec: str) -> ProjectSource:
    """Parse a `slug=/absolute/docs/root` CLI mapping."""
    slug, separator, raw_root = spec.partition("=")
    if separator == "" or slug.strip() == "" or raw_root.strip() == "":
        raise VaultError.invalid_source_spec(spec)
    return ProjectSource(slug=slug.strip(), docs_root=Path(raw_root.strip()))


def _validated_sources(sources: Sequence[ProjectSource]) -> list[ProjectSource]:
    seen: set[str] = set()
    validated: list[ProjectSource] = []
    for source in sorted(sources, key=lambda item: item.slug):
        if PROJECT_SLUG_PATTERN.fullmatch(source.slug) is None:
            raise VaultError.invalid_source_slug(source.slug)
        if source.slug in seen:
            raise VaultError.duplicate_slug(source.slug)
        seen.add(source.slug)
        root = source.docs_root.expanduser().resolve()
        if not root.is_dir():
            raise VaultError.missing_root(source.docs_root)
        validated.append(ProjectSource(slug=source.slug, docs_root=root))
    return validated


def _plan_source(
    home: Path, source: ProjectSource
) -> tuple[list[VaultEntry], list[Path]]:
    root = source.docs_root
    included = list(iter_markdown_files(root))
    skipped = [path for path in sorted(root.rglob("*.md")) if path not in included]

    namespace = home / "docs" / PROJECTS_DIR / source.slug
    project_tag = f"project:{source.slug}"
    hub_target = namespace / "index.md"
    hub_link = f"{PROJECTS_DIR}/{source.slug}/index"

    entries: list[VaultEntry] = []
    note_links: list[str] = []
    hub_source_raw: str | None = None
    for path in included:
        relative = path.relative_to(root)
        raw = path.read_text(encoding="utf-8")
        if relative == Path("index.md"):
            hub_source_raw = raw
            continue
        rendered = upsert_frontmatter_tags(raw, (project_tag,))
        rendered = ensure_managed_wikilink(rendered, hub_link)
        entries.append(
            VaultEntry(
                source=path,
                target=namespace / relative,
                source_sha256=_sha256(raw.encode("utf-8")),
                rendered_sha256=_sha256(rendered.encode("utf-8")),
                action="create",
                rendered=rendered,
            )
        )
        note_links.append(f"{PROJECTS_DIR}/{source.slug}/{relative.with_suffix('')}")

    hub_base = (
        hub_source_raw
        if hub_source_raw is not None
        else HUB_TEMPLATE.format(title=f"{source.slug} Project Index")
    )
    hub_rendered = upsert_frontmatter_tags(hub_base, (project_tag,))
    hub_rendered = replace_managed_block(
        hub_rendered,
        NOTES_BLOCK,
        tuple(f"- [[{link}]]" for link in sorted(note_links)),
    )
    entries.append(
        VaultEntry(
            source=root / "index.md",
            target=hub_target,
            source_sha256=_sha256(
                b"" if hub_source_raw is None else hub_source_raw.encode("utf-8")
            ),
            rendered_sha256=_sha256(hub_rendered.encode("utf-8")),
            action="create",
            rendered=hub_rendered,
        )
    )
    return entries, skipped


def _plan_global_index(home: Path, hub_links: Sequence[str]) -> VaultEntry:
    """Plan the managed projects block inside the native global index.

    Only the `llm-wiki:projects` block is owned by the tool; the rest of the
    file is user content, so this entry is exempt from the conflict rule.
    """
    index_path = home / "docs" / "index.md"
    base = (
        index_path.read_text(encoding="utf-8")
        if index_path.is_file()
        else GLOBAL_INDEX_TEMPLATE
    )
    rendered = replace_managed_block(
        base,
        PROJECTS_BLOCK,
        tuple(f"- [[{link}]]" for link in sorted(hub_links)),
    )
    return VaultEntry(
        source=index_path,
        target=index_path,
        source_sha256=_sha256(base.encode("utf-8")),
        rendered_sha256=_sha256(rendered.encode("utf-8")),
        action="update" if index_path.is_file() else "create",
        rendered=rendered,
    )


def _with_action(entry: VaultEntry, owned_state: dict[str, str]) -> VaultEntry:
    if entry.source == entry.target:
        # The global index owns only its managed block; its base is read from
        # the current file at plan time, so user edits survive and it is
        # never a conflict.
        if not entry.target.is_file():
            return _replace_action(entry, "create")
        current_sha = _target_sha(entry.target)
        action = "unchanged" if current_sha == entry.rendered_sha256 else "update"
        return _replace_action(entry, action)
    if not entry.target.exists():
        return _replace_action(entry, "create")
    action, reason = _existing_target_action(entry, owned_state)
    return _replace_action(entry, action, reason=reason)


def _existing_target_action(
    entry: VaultEntry, owned_state: dict[str, str]
) -> tuple[VaultAction, str]:
    current_sha = _target_sha(entry.target)
    if current_sha == entry.rendered_sha256:
        return "unchanged", ""
    last_applied_sha = owned_state.get(str(entry.target))
    if last_applied_sha is None:
        return "conflict", "unmanaged"
    if current_sha != last_applied_sha:
        # Three-way check: the target differs from both the last applied
        # rendering and the new rendering — someone edited the vault copy.
        # Overwriting would silently destroy that edit.
        return "conflict", "locally-modified"
    return "update", ""


def _target_sha(target: Path) -> str:
    return _sha256(target.read_bytes())


def _replace_action(
    entry: VaultEntry, action: VaultAction, reason: str = ""
) -> VaultEntry:
    if entry.action == action and entry.conflict_reason == reason:
        return entry
    return VaultEntry(
        source=entry.source,
        target=entry.target,
        source_sha256=entry.source_sha256,
        rendered_sha256=entry.rendered_sha256,
        action=action,
        rendered=entry.rendered,
        conflict_reason=reason,
    )


def _target_key(entry: VaultEntry) -> str:
    return str(entry.target)


def _owned_state(home: Path) -> dict[str, str]:
    """Map each managed target to the rendered hash it was last applied with.

    Later manifests override earlier ones, so the value reflects the most
    recent applied state — the baseline for detecting vault-side edits.
    """
    manifest_dir = home / MANIFEST_DIR
    if not manifest_dir.is_dir():
        return {}
    owned: dict[str, str] = {}
    for manifest_path in sorted(manifest_dir.glob("vault-manifest-*.json")):
        try:
            data: object = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        mapping: dict[object, object] = dict(data)  # pyright: ignore[reportUnknownArgumentType]
        if mapping.get("status") != "applied":
            continue
        entries = mapping.get("entries")
        if not isinstance(entries, list):
            continue
        raw_entries: list[object] = list(entries)  # pyright: ignore[reportUnknownArgumentType]
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            entry_mapping: dict[object, object] = dict(raw_entry)  # pyright: ignore[reportUnknownArgumentType]
            target = entry_mapping.get("target")
            rendered = entry_mapping.get("rendered_sha256")
            if isinstance(target, str) and isinstance(rendered, str):
                owned[target] = rendered
    return owned


def _write_manifest(
    plan: VaultPlan,
    status: str,
    manifest_path: Path | None = None,
) -> Path:
    manifest_dir = plan.home / MANIFEST_DIR
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path is None:
        existing = sorted(manifest_dir.glob("vault-manifest-*.json"))
        manifest_path = manifest_dir / f"vault-manifest-{len(existing) + 1:04d}.json"

    payload = {
        "version": MANIFEST_VERSION,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "tool_commit": _git_value(Path(__file__).parent, "rev-parse", "HEAD"),
        "home": str(plan.home),
        "sources": [
            {
                "slug": source.slug,
                "root": str(source.docs_root),
                "git_root": _git_value(
                    source.docs_root, "rev-parse", "--show-toplevel"
                ),
                "branch": _git_value(
                    source.docs_root, "rev-parse", "--abbrev-ref", "HEAD"
                ),
                "commit": _git_value(source.docs_root, "rev-parse", "HEAD"),
            }
            for source in plan.sources
        ],
        "entries": [
            {
                "source": str(entry.source),
                "target": str(entry.target),
                "source_sha256": entry.source_sha256,
                "rendered_sha256": entry.rendered_sha256,
                "action": entry.action,
                "conflict_reason": entry.conflict_reason,
            }
            for entry in plan.entries
        ],
        "skipped": [str(path) for path in plan.skipped],
        "conflicts": [str(entry.target) for entry in plan.conflicts],
    }
    _ = manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def _git_value(path: Path, *args: str) -> str | None:
    git_executable = shutil.which("git")
    if git_executable is None:
        return None
    try:
        # Arguments are fixed git subcommands plus locally-configured paths.
        completed = subprocess.run(  # noqa: S603
            [git_executable, "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value if value != "" else None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
