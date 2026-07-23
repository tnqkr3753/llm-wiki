"""Git post-commit hook installer for automatic re-indexing."""

from pathlib import Path

from rich.console import Console

console = Console()


def install_git_hook(project_path: Path | None = None, force: bool = False) -> Path:
    """Install a Git post-commit hook that automatically reindexes LLM Wiki documents."""
    resolved_path = (project_path or Path.cwd()).expanduser().resolve()
    git_dir = resolved_path / ".git"

    if not git_dir.is_dir():
        console.print(f"[red]Error:[/red] No `.git` directory found at {resolved_path}")
        raise ValueError(f"Not a git repository: {resolved_path}")

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_script = hooks_dir / "post-commit"

    if hook_script.exists() and not force:
        console.print(
            f"[yellow]Git post-commit hook already exists at {hook_script}.[/yellow] Use --force to overwrite."
        )
        return hook_script

    script_content = """#!/bin/sh
# LLM Wiki post-commit auto-reindex hook
if command -v llm-wiki >/dev/null 2>&1; then
    llm-wiki reindex -p "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 &
fi
"""

    hook_script.write_text(script_content, encoding="utf-8")
    hook_script.chmod(0o755)

    console.print(f"[green]✓ Installed Git post-commit hook:[/green] {hook_script}")
    return hook_script
