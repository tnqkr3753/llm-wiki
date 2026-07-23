"""System & workspace diagnostic tools for LLM Wiki."""

import json
import sqlite3
import sys
from pathlib import Path

from rich.console import Console

from llm_wiki.agents import ALL_TARGETS

console = Console()


def run_doctor(project_path: Path | None = None) -> None:
    """Run diagnostics on Python, SQLite FTS5, project config, skills, and hooks."""
    target_path = (project_path or Path.cwd()).expanduser().resolve()
    console.print(f"[bold blue]LLM Wiki System & Workspace Diagnostics[/bold blue]")
    console.print(f"Target Directory: {target_path}\n")

    # 1. Python Environment
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"[green]✓[/green] Python Version: {py_ver}")

    # 2. SQLite & FTS5 Trigram Support
    sqlite_ver = sqlite3.sqlite_version
    trigram_ok = check_fts5_trigram_support()
    if trigram_ok:
        console.print(
            f"[green]✓[/green] SQLite Version: {sqlite_ver} (FTS5 Trigram Tokenizer Supported)"
        )
    else:
        console.print(
            f"[yellow]![/yellow] SQLite Version: {sqlite_ver} (FTS5 Trigram fallback to unicode61)"
        )

    # 3. Workspace Config & DB Health
    wiki_config = target_path / ".llm-wiki" / "config.toml"
    wiki_db = target_path / ".llm-wiki" / "wiki.db"
    if wiki_config.is_file():
        console.print(f"[green]✓[/green] Project Config: {wiki_config}")
    else:
        console.print(
            f"[yellow]![/yellow] Project Config: Not found at {wiki_config} (Run `llm-wiki init`)"
        )

    if wiki_db.is_file():
        doc_count = count_indexed_documents(wiki_db)
        console.print(f"[green]✓[/green] Wiki Database: {wiki_db} ({doc_count} documents indexed)")
    else:
        console.print(f"[yellow]![/yellow] Wiki Database: Not found at {wiki_db}")

    # 4. Agent Skills & Hooks Inspection
    console.print("\n[bold]Agent Skill & Hook Installations:[/bold]")
    for target in ALL_TARGETS:
        hook_script = target_path / target.hook_script_rel
        if hook_script.is_file():
            console.print(
                f"  [green]✓[/green] {target.display_name} Hook Script: {hook_script}"
            )
        else:
            console.print(
                f"  [dim]-[/dim] {target.display_name} Hook Script: Not installed ({target.install_hooks_command})"
            )


from contextlib import closing


def check_fts5_trigram_support() -> bool:
    try:
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.execute(
                "CREATE VIRTUAL TABLE test_fts USING fts5(body, tokenize='trigram')"
            )
            return True
    except Exception:
        return False


def count_indexed_documents(db_path: Path) -> int:
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0
