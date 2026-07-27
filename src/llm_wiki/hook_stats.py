"""Hook statistics and token savings tracking."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from rich.console import Console
from rich.table import Table

console = Console()

CHARS_PER_TOKEN = 3.5
MAX_SESSION_ROWS = 10
SESSION_ID_WIDTH = 20


@dataclass(frozen=True, slots=True)
class SessionStats:
    """Deduplication statistics recorded by one hook session."""

    session_id: str
    cwd: str
    hits: int
    saved_chars: int

    @property
    def est_tokens(self) -> int:
        """Estimate the tokens saved by this session's deduplication."""
        return int(self.saved_chars / CHARS_PER_TOKEN)


def show_hook_stats() -> None:
    """Analyze session state files in tempdir and report token savings."""
    temp_dir = Path(tempfile.gettempdir())
    session_files = list(temp_dir.glob("llm_wiki_session_*.json"))
    sessions = [
        stats
        for stats in (_read_session_stats(path) for path in session_files)
        if stats is not None
    ]

    total_saved_chars = sum(stats.saved_chars for stats in sessions)
    total_dedup_hits = sum(stats.hits for stats in sessions)
    est_total_tokens = int(total_saved_chars / CHARS_PER_TOKEN)

    console.print("[bold blue]LLM Wiki Hook Performance & Token Savings[/bold blue]")
    console.print(f"Total Tracked Sessions: {len(session_files)}")
    console.print(f"Total Deduplication Hits: [green]{total_dedup_hits}[/green] times")
    console.print(f"Total Saved Characters: [green]{total_saved_chars:,}[/green] chars")
    console.print(
        f"Estimated Token Savings: [bold green]~{est_total_tokens:,}[/bold green] "
        "tokens\n"
    )

    active = [stats for stats in sessions if stats.hits > 0]
    if active:
        console.print(_build_session_table(active))


def _read_session_stats(path: Path) -> SessionStats | None:
    """Parse one session state file, or return None when it is unusable."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A truncated or unreadable session file is not worth failing on.
        return None
    if not isinstance(raw, dict):
        return None

    # JSON object keys are always strings; the values stay untrusted and are
    # validated field by field below.
    data = cast("dict[str, object]", raw)
    return SessionStats(
        session_id=_str_field(data, "session_id", path.stem)[:SESSION_ID_WIDTH],
        cwd=_str_field(data, "cwd", "unknown"),
        hits=_int_field(data, "dedup_hits"),
        saved_chars=_int_field(data, "saved_chars"),
    )


def _str_field(data: dict[str, object], key: str, default: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else default


def _int_field(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    return value if isinstance(value, int) else 0


def _build_session_table(sessions: list[SessionStats]) -> Table:
    table = Table(title="Active Session Performance")
    table.add_column("Session ID", style="cyan")
    table.add_column("Directory", style="magenta")
    table.add_column("Hits", justify="right", style="green")
    table.add_column("Saved Chars", justify="right", style="green")
    table.add_column("Est. Tokens", justify="right", style="bold green")

    for stats in sessions[:MAX_SESSION_ROWS]:
        table.add_row(
            stats.session_id,
            stats.cwd,
            str(stats.hits),
            f"{stats.saved_chars:,}",
            f"{stats.est_tokens:,}",
        )
    return table
