"""Continuous file watcher for auto-indexing markdown changes."""

import time
from pathlib import Path

from rich.console import Console

from llm_wiki.config import resolve_db_path
from llm_wiki.store import reindex_directory

console = Console()


def run_watcher(project_path: Path | None = None, interval: float = 2.0) -> None:
    """Watch project markdown files and automatically reindex on change."""
    target_path = (project_path or Path.cwd()).expanduser().resolve()
    db_path = resolve_db_path(None)
    console.print(
        f"[bold blue]LLM Wiki File Watcher Active[/bold blue] ({target_path})"
    )
    console.print("Press Ctrl+C to stop watching.\n")

    mtime_cache: dict[Path, float] = {}

    def scan_md_files() -> dict[Path, float]:
        current: dict[Path, float] = {}
        for file_path in target_path.rglob("*.md"):
            # Exclude hidden directories and venvs
            if any(part.startswith(".") or part in ("venv", "node_modules", "__pycache__") for part in file_path.parts):
                continue
            try:
                current[file_path] = file_path.stat().st_mtime
            except Exception:
                pass
        return current

    mtime_cache = scan_md_files()
    console.print(f"Tracking [green]{len(mtime_cache)}[/green] markdown files...")

    try:
        while True:
            time.sleep(interval)
            latest = scan_md_files()
            changed = False

            for path, mtime in latest.items():
                if path not in mtime_cache or mtime_cache[path] != mtime:
                    console.print(f"[yellow]Modified:[yellow] {path.relative_to(target_path)}")
                    changed = True
                    break

            if not changed:
                deleted = set(mtime_cache.keys()) - set(latest.keys())
                if deleted:
                    console.print(f"[red]Deleted file detected.[/red]")
                    changed = True

            if changed:
                mtime_cache = latest
                console.print("Re-indexing wiki database...")
                try:
                    count = reindex_directory(db_path, target_path)
                    console.print(
                        f"[green]✓ Re-indexed {count} documents.[/green]\n"
                    )
                except Exception as exc:
                    console.print(f"[red]Failed to reindex: {exc}[/red]\n")
    except KeyboardInterrupt:
        console.print("\n[dim]Watcher stopped.[/dim]")
