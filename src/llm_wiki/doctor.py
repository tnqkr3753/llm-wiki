"""System & workspace diagnostic tools for LLM Wiki."""

import sqlite3
import sys
import tomllib
from contextlib import closing
from pathlib import Path

from rich.console import Console

from llm_wiki.agents import ALL_TARGETS
from llm_wiki.config import resolve_home_path
from llm_wiki.embedding import describe_settings, resolve_embedding_settings
from llm_wiki.errors import WikiError
from llm_wiki.global_vault import audit_global_vault

console = Console()

GLOBAL_DB_HINT = "~/.llm-wiki/wiki.db"


def run_doctor(project_path: Path | None = None) -> None:
    """Run diagnostics on Python, SQLite FTS5, project config, skills, and hooks."""
    target_path = (project_path or Path.cwd()).expanduser().resolve()
    console.print("[bold blue]LLM Wiki System & Workspace Diagnostics[/bold blue]")
    console.print(f"Target Directory: {target_path}\n")

    # 1. Python Environment
    py_ver = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    console.print(f"[green]✓[/green] Python Version: {py_ver}")

    # 2. SQLite & FTS5 Trigram Support
    sqlite_ver = sqlite3.sqlite_version
    trigram_ok = check_fts5_trigram_support()
    if trigram_ok:
        console.print(
            f"[green]✓[/green] SQLite Version: {sqlite_ver} "
            "(FTS5 Trigram Tokenizer Supported)"
        )
    else:
        console.print(
            f"[yellow]![/yellow] SQLite Version: {sqlite_ver} "
            "(FTS5 Trigram fallback to unicode61)"
        )

    # 3. Workspace Config & DB Health
    wiki_config = target_path / ".llm-wiki" / "config.toml"
    wiki_db = target_path / ".llm-wiki" / "wiki.db"
    if wiki_config.is_file():
        console.print(f"[green]✓[/green] Project Config: {wiki_config}")
    else:
        console.print(
            f"[yellow]![/yellow] Project Config: Not found at {wiki_config} "
            "(Run `llm-wiki init`)"
        )

    if wiki_db.is_file():
        doc_count = count_indexed_documents(wiki_db)
        console.print(
            f"[green]✓[/green] Wiki Database: {wiki_db} ({doc_count} documents indexed)"
        )
    else:
        console.print(f"[yellow]![/yellow] Wiki Database: Not found at {wiki_db}")

    # 4. Embedding configuration (retrieval stays BM25 until a backend exists)
    try:
        settings = resolve_embedding_settings(target_path)
    except WikiError as exc:
        console.print(f"[yellow]![/yellow] Embedding: config unreadable ({exc})")
    else:
        marker = (
            "[yellow]![/yellow]"
            if settings is not None and settings.is_blocked
            else ("[green]✓[/green]" if settings is not None else "[dim]-[/dim]")
        )
        console.print(f"{marker} Embedding: {describe_settings(settings)}")
        if settings is not None and wiki_db.is_file():
            console.print(
                f"  Vectors: {describe_vector_cache(wiki_db, settings.model)}"
            )

    # 5. Agent Skills & Hooks Inspection
    console.print("\n[bold]Agent Skill & Hook Installations:[/bold]")
    for target in ALL_TARGETS:
        hook_script = target_path / target.hook_script_rel
        if hook_script.is_file():
            console.print(
                f"  [green]✓[/green] {target.display_name} Hook Script: {hook_script}"
            )
        else:
            console.print(
                f"  [dim]-[/dim] {target.display_name} Hook Script: Not installed "
                f"({target.install_hooks_command})"
            )

    # 6. Global-wiki alignment warnings (read-only)
    _check_project_mode(target_path)
    _check_vault_alignment()


def _check_project_mode(target_path: Path) -> None:
    """Warn on legacy implicit-isolated configs and stale global-mode text."""
    config_path = target_path / ".llm-wiki" / "config.toml"
    if not config_path.is_file():
        return
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        console.print(f"[yellow]![/yellow] Project config unreadable: {config_path}")
        return

    if "mode" not in data and "db_path" in data:
        console.print(
            "[yellow]![/yellow] Legacy implicit-isolated config: add "
            f'mode = "isolated" (or migrate to global mode) in {config_path}'
        )
    if data.get("mode") == "global":
        _warn_stale_local_db_text(target_path)


def _warn_stale_local_db_text(target_path: Path) -> None:
    """Warn when generated instructions still prefer a local DB in global mode."""
    local_db = target_path / ".llm-wiki" / "wiki.db"
    agents_path = target_path / "AGENTS.md"
    if agents_path.is_file():
        try:
            agents_text = agents_path.read_text(encoding="utf-8")
        except OSError:
            agents_text = ""
        if str(local_db) in agents_text:
            console.print(
                "[yellow]![/yellow] Stale AGENTS.md points at the local DB "
                f"while project mode is global: {agents_path}"
            )

    for target in ALL_TARGETS:
        skills_root = target.default_skills_dir.expanduser()
        for skill_file in sorted(skills_root.glob("llm-wiki-*/SKILL.md")):
            try:
                skill_text = skill_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if GLOBAL_DB_HINT not in skill_text:
                console.print(
                    "[yellow]![/yellow] Stale generated skill lacks the global "
                    f"DB contract ({GLOBAL_DB_HINT}): {skill_file}"
                )


def _check_vault_alignment() -> None:
    """Warn when the global DB and the physical vault disagree."""
    home = resolve_home_path(None)
    db_path = _global_db_path(home)
    if not db_path.is_file():
        return
    try:
        audit = audit_global_vault(home, db_path)
    except (WikiError, sqlite3.Error, OSError):
        console.print(f"[yellow]![/yellow] Vault audit failed for {db_path}")
        return

    if audit.external_index_paths:
        console.print(
            f"[yellow]![/yellow] {len(audit.external_index_paths)} indexed "
            f"document(s) outside the global docs root {home / 'docs'}"
        )
    internal_indexed = audit.indexed_documents - len(audit.external_index_paths)
    if audit.markdown_files > internal_indexed:
        console.print(
            f"[yellow]![/yellow] {audit.markdown_files - internal_indexed} "
            "physical Markdown file(s) not present in the global DB "
            "(run `llm-wiki reindex`)"
        )
    missing = _missing_indexed_files(db_path, home / "docs")
    if missing:
        console.print(
            f"[yellow]![/yellow] {missing} indexed document(s) missing on disk "
            "(run `llm-wiki reindex`)"
        )
    if audit.orphan_paths:
        console.print(
            f"[yellow]![/yellow] {len(audit.orphan_paths)} orphan Markdown "
            "node(s) without resolved links"
        )
    if audit.unresolved_targets:
        console.print(
            f"[yellow]![/yellow] {len(audit.unresolved_targets)} unresolved "
            "wikilink target(s)"
        )


def _global_db_path(home: Path) -> Path:
    config_path = home / "config.toml"
    if config_path.is_file():
        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return home / "wiki.db"
        value = data.get("db_path")
        if isinstance(value, str) and value.strip() != "":
            candidate = Path(value).expanduser()
            return candidate if candidate.is_absolute() else home / candidate
    return home / "wiki.db"


def _missing_indexed_files(db_path: Path, docs_root: Path) -> int:
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            rows = conn.execute("SELECT path FROM documents").fetchall()
    except sqlite3.Error:
        return 0
    return sum(
        1
        for row in rows
        if Path(str(row[0])).is_relative_to(docs_root)
        and not Path(str(row[0])).is_file()
    )


def describe_vector_cache(db_path: Path, model: str) -> str:
    """Summarize how much of the chunk index this model has vectors for."""
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            chunks = conn.execute(
                "SELECT COUNT(DISTINCT content_hash) FROM document_chunks"
            ).fetchone()
            vectors = conn.execute(
                "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?",
                (model,),
            ).fetchone()
    except sqlite3.Error:
        return "not built yet (run `llm-wiki embed`)"
    total = int(chunks[0]) if chunks else 0
    stored = int(vectors[0]) if vectors else 0
    if total == 0:
        return "no chunks indexed (run `llm-wiki reindex`)"
    if stored == 0:
        return f"0 of {total} chunks embedded (run `llm-wiki embed`)"
    if stored < total:
        return f"{stored} of {total} chunks embedded — hybrid search partially active"
    return f"{stored} of {total} chunks embedded — hybrid search active"


def check_fts5_trigram_support() -> bool:
    """Report whether this SQLite build offers the FTS5 trigram tokenizer."""
    try:
        with closing(sqlite3.connect(":memory:")) as conn:
            _ = conn.execute(
                "CREATE VIRTUAL TABLE test_fts USING fts5(body, tokenize='trigram')"
            )
    except sqlite3.Error:
        return False
    return True


def count_indexed_documents(db_path: Path) -> int:
    """Count indexed documents, returning 0 when the database is unusable."""
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0
