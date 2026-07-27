"""Continuous file watcher for auto-indexing markdown changes."""

import time
from pathlib import Path
from typing import Final

from rich.console import Console

from llm_wiki.config import resolve_db_path
from llm_wiki.errors import WikiError
from llm_wiki.store import iter_markdown_files, reindex_directory

console = Console()

DEFAULT_INTERVAL: Final = 2.0

type MtimeSnapshot = dict[Path, float]


def run_watcher(
    project_path: Path | None = None,
    interval: float = DEFAULT_INTERVAL,
) -> None:
    """Watch project markdown files and automatically reindex on change."""
    target_path = (project_path or Path.cwd()).expanduser().resolve()
    db_path = resolve_db_path(None)
    console.print(
        f"[bold blue]LLM Wiki File Watcher Active[/bold blue] ({target_path})"
    )
    console.print("Press Ctrl+C to stop watching.\n")

    snapshot = scan_mtimes(target_path)
    console.print(f"Tracking [green]{len(snapshot)}[/green] markdown files...")

    try:
        while True:
            time.sleep(interval)
            latest = scan_mtimes(target_path)
            if latest == snapshot:
                continue

            for line in describe_changes(snapshot, latest, target_path):
                console.print(line)
            snapshot = latest
            _reindex_once(db_path, target_path)
    except KeyboardInterrupt:
        console.print("\n[dim]Watcher stopped.[/dim]")


def scan_mtimes(target_path: Path) -> MtimeSnapshot:
    """Collect modification times for every indexable markdown file."""
    snapshot: MtimeSnapshot = {}
    for file_path in iter_markdown_files(target_path):
        try:
            snapshot[file_path] = file_path.stat().st_mtime
        except OSError:
            # The file vanished mid-scan; the next pass reports it as deleted.
            continue
    return snapshot


def describe_changes(
    previous: MtimeSnapshot,
    latest: MtimeSnapshot,
    target_path: Path,
) -> tuple[str, ...]:
    """Render one console line per added, modified, or deleted file."""
    added = [
        f"[green]Added:[/green] {path.relative_to(target_path)}"
        for path in sorted(set(latest) - set(previous))
    ]
    modified = [
        f"[yellow]Modified:[/yellow] {path.relative_to(target_path)}"
        for path in sorted(set(previous) & set(latest))
        if previous[path] != latest[path]
    ]
    deleted = [
        f"[red]Deleted:[/red] {path.relative_to(target_path)}"
        for path in sorted(set(previous) - set(latest))
    ]
    return (*added, *modified, *deleted)


def _reindex_once(db_path: Path, target_path: Path) -> None:
    console.print("Re-indexing wiki database...")
    try:
        result = reindex_directory(db_path, target_path)
    except WikiError as exc:
        console.print(f"[red]Failed to reindex: {exc}[/red]\n")
        return

    console.print(
        f"[green]✓ Re-indexed {result.indexed} documents "
        f"({result.removed} removed).[/green]"
    )
    for failure in result.failures:
        console.print(f"[red]  ! {failure.path}: {failure.reason}[/red]")
    console.print("")
