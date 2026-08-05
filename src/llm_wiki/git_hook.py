"""Git hook installers for automatic re-indexing and vault synchronization."""

from pathlib import Path

from rich.console import Console

from llm_wiki.config import (
    PROJECT_TAG_PREFIX,
    WikiMode,
    resolve_db_path,
    resolve_home_path,
    resolve_project_config,
)
from llm_wiki.errors import ConfigReadError, GitRepositoryError

console = Console()

SYNC_HOOK_NAMES = ("post-merge", "post-checkout")


def install_git_hook(project_path: Path | None = None, force: bool = False) -> Path:
    """Install a Git post-commit hook that reindexes LLM Wiki documents."""
    resolved_path = (project_path or Path.cwd()).expanduser().resolve()
    git_dir = resolved_path / ".git"

    if not git_dir.is_dir():
        console.print(f"[red]Error:[/red] No `.git` directory found at {resolved_path}")
        raise GitRepositoryError.missing(resolved_path)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_script = hooks_dir / "post-commit"

    if hook_script.exists() and not force:
        console.print(
            f"[yellow]Git post-commit hook already exists at {hook_script}.[/yellow] "
            "Use --force to overwrite."
        )
        return hook_script

    script_content = """#!/bin/sh
# LLM Wiki post-commit auto-reindex hook
if command -v llm-wiki >/dev/null 2>&1; then
    llm-wiki reindex -p "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 &
fi
"""

    _ = hook_script.write_text(script_content, encoding="utf-8")
    hook_script.chmod(0o755)

    console.print(f"[green]✓ Installed Git post-commit hook:[/green] {hook_script}")
    return hook_script


def install_sync_hook(
    project_path: Path | None = None, force: bool = False
) -> tuple[Path, ...]:
    """Install post-merge/post-checkout hooks that keep the wiki in sync.

    After a pull or branch switch, a global-mode project re-imports its docs
    into the shared vault and reindexes the global DB, so retrieval always
    reads the project git's latest state. Isolated projects just reindex
    their local DB.
    """
    resolved_path = (project_path or Path.cwd()).expanduser().resolve()
    git_dir = resolved_path / ".git"
    if not git_dir.is_dir():
        console.print(f"[red]Error:[/red] No `.git` directory found at {resolved_path}")
        raise GitRepositoryError.missing(resolved_path)

    config = resolve_project_config(resolved_path)
    if config is None:
        raise ConfigReadError.invalid(resolved_path / ".llm-wiki" / "config.toml")

    script_content = _sync_script(resolved_path)
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    installed: list[Path] = []
    for hook_name in SYNC_HOOK_NAMES:
        hook_script = hooks_dir / hook_name
        if hook_script.exists() and not force:
            console.print(
                f"[yellow]Git {hook_name} hook already exists at {hook_script}."
                "[/yellow] Use --force to overwrite."
            )
            continue
        _ = hook_script.write_text(script_content, encoding="utf-8")
        hook_script.chmod(0o755)
        console.print(f"[green]✓ Installed Git {hook_name} hook:[/green] {hook_script}")
        installed.append(hook_script)
    return tuple(installed)


def _sync_script(project_root: Path) -> str:
    """Render the sync hook body with install-time resolved scope."""
    config = resolve_project_config(project_root)
    db_path = resolve_db_path(None, project_root)

    if (
        config is not None
        and config.mode is WikiMode.GLOBAL
        and config.project_tag is not None
    ):
        slug = config.project_tag.removeprefix(PROJECT_TAG_PREFIX)
        home = resolve_home_path(None)
        return f"""#!/bin/sh
# LLM Wiki sync hook: mirror project docs into the shared vault after pull
if command -v llm-wiki >/dev/null 2>&1; then
    if ! llm-wiki vault import --source {slug}={config.docs_dir} \\
        --home {home} --apply >/dev/null 2>&1; then
        echo "[llm-wiki] vault sync skipped: import reported a conflict;" \\
            "run 'llm-wiki vault import --source {slug}={config.docs_dir}" \\
            "--home {home}' to inspect"
    fi
    llm-wiki reindex -p {home / "docs"} --db {db_path} >/dev/null 2>&1 &
fi
exit 0
"""

    return f"""#!/bin/sh
# LLM Wiki sync hook: reindex the isolated project wiki after pull
if command -v llm-wiki >/dev/null 2>&1; then
    llm-wiki reindex -p "$(git rev-parse --show-toplevel)" \\
        --db {db_path} >/dev/null 2>&1 &
fi
exit 0
"""
