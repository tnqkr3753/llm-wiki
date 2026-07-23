"""Hook statistics and token savings tracking."""

import json
import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def show_hook_stats() -> None:
    """Analyze session state files in tempdir and report token savings statistics."""
    temp_dir = Path(tempfile.gettempdir())
    session_files = list(temp_dir.glob("llm_wiki_session_*.json"))

    total_sessions = len(session_files)
    total_dedup_hits = 0
    total_saved_chars = 0

    sessions_detail = []

    for s_file in session_files:
        try:
            data = json.loads(s_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                hits = int(data.get("dedup_hits", 0))
                saved_chars = int(data.get("saved_chars", 0))
                session_id = data.get("session_id", s_file.stem)
                cwd = data.get("cwd", "unknown")

                total_dedup_hits += hits
                total_saved_chars += saved_chars

                if hits > 0:
                    sessions_detail.append(
                        {
                            "session_id": session_id[:20],
                            "cwd": cwd,
                            "hits": hits,
                            "saved_chars": saved_chars,
                            "est_tokens": int(saved_chars / 3.5),
                        }
                    )
        except Exception:
            pass

    est_total_tokens = int(total_saved_chars / 3.5)

    console.print("[bold blue]LLM Wiki Hook Performance & Token Savings[/bold blue]")
    console.print(f"Total Tracked Sessions: {total_sessions}")
    console.print(f"Total Deduplication Hits: [green]{total_dedup_hits}[/green] times")
    console.print(f"Total Saved Characters: [green]{total_saved_chars:,}[/green] chars")
    console.print(
        f"Estimated Token Savings: [bold green]~{est_total_tokens:,}[/bold green] tokens\n"
    )

    if sessions_detail:
        table = Table(title="Active Session Performance")
        table.add_column("Session ID", style="cyan")
        table.add_column("Directory", style="magenta")
        table.add_column("Hits", justify="right", style="green")
        table.add_column("Saved Chars", justify="right", style="green")
        table.add_column("Est. Tokens", justify="right", style="bold green")

        for item in sessions_detail[:10]:
            table.add_row(
                item["session_id"],
                item["cwd"],
                str(item["hits"]),
                f"{item['saved_chars']:,}",
                f"{item['est_tokens']:,}",
            )
        console.print(table)
