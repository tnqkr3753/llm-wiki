"""Typer command surface for LLM Wiki."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from llm_wiki.agent_hooks import (
    install_agent_hooks,
    install_startup_hook,
    uninstall_agent_hooks,
)
from llm_wiki.agent_skills import SkillLanguage, install_agent_skills
from llm_wiki.agents import CLAUDE_TARGET, CODEX_TARGET, GEMINI_TARGET, AgentTarget
from llm_wiki.config import resolve_db_path
from llm_wiki.errors import WikiError
from llm_wiki.init_project import InitResult, initialize_global, initialize_project
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import DocumentId
from llm_wiki.store import get_document, search, upsert_document

from llm_wiki.doctor import run_doctor
from llm_wiki.git_hook import install_git_hook
from llm_wiki.hook_stats import show_hook_stats
from llm_wiki.watcher import run_watcher

DEFAULT_LIMIT = 5

app = typer.Typer(no_args_is_help=True)
codex_app = typer.Typer(no_args_is_help=True)
claude_app = typer.Typer(no_args_is_help=True)
gemini_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
git_hook_app = typer.Typer(no_args_is_help=True)
console = Console(markup=False, width=1000)

DbOption = Annotated[
    Path | None,
    typer.Option(
        "--db",
        help="Path to the SQLite wiki database.",
        dir_okay=False,
        writable=True,
    ),
]
LimitOption = Annotated[
    int,
    typer.Option("--limit", min=1, max=20, help="Maximum number of results."),
]
ProjectPathOption = Annotated[
    Path | None,
    typer.Option(
        "-p",
        "--path",
        help="Project directory to initialize.",
        file_okay=False,
        writable=True,
    ),
]
HomeOption = Annotated[
    Path | None,
    typer.Option(
        "--home",
        help="Global LLM Wiki home directory.",
        file_okay=False,
        writable=True,
    ),
]
SkillsDirOption = Annotated[
    Path | None,
    typer.Option(
        "--skills-dir",
        help="Codex skills directory.",
        file_okay=False,
        writable=True,
    ),
]
ToolPathOption = Annotated[
    Path | None,
    typer.Option(
        "--tool-path",
        help="LLM Wiki checkout path for uv-run fallback instructions.",
        file_okay=False,
        writable=True,
    ),
]
LanguageOption = Annotated[
    SkillLanguage,
    typer.Option(
        "--language",
        help="Generated skill language.",
    ),
]
SkillForceOption = Annotated[
    bool,
    typer.Option("--force", help="Overwrite existing generated LLM Wiki skills."),
]
HookForceOption = Annotated[
    bool,
    typer.Option("--force", help="Overwrite the generated hook script."),
]


app.add_typer(codex_app, name="codex", help="Install Codex integrations.")
app.add_typer(claude_app, name="claude", help="Install Claude Code integrations.")
app.add_typer(gemini_app, name="gemini", help="Install Gemini CLI integrations.")
app.add_typer(project_app, name="project", help="Manage project-local wiki state.")
app.add_typer(git_hook_app, name="git-hook", help="Manage Git hooks for LLM Wiki.")


@app.command()
def init(
    home: HomeOption = None,
) -> None:
    """Initialize the global LLM Wiki home."""
    result = initialize_global(home)
    _print_init_result(result)


@project_app.command("init")
def project_init(
    path: ProjectPathOption = None,
    agents: Annotated[
        bool,
        typer.Option(
            "--agents",
            help="Write AGENTS.md instructions for Codex integration.",
        ),
    ] = False,
) -> None:
    """Initialize an LLM Wiki layout for a project."""
    project_path = Path.cwd() if path is None else path
    result = initialize_project(project_path, include_agents=agents)
    _print_init_result(result)


def _print_init_result(result: InitResult) -> None:
    console.print(f"initialized {result.scope} {result.project_path}")
    console.print(f"db: {result.db_path}")
    console.print(f"config: {result.config_path}")
    console.print(f"index: {result.index_path}")
    if result.agents_path is not None:
        console.print(f"agents: {result.agents_path}")


def _register_install_commands(agent_app: typer.Typer, target: AgentTarget) -> None:
    def install_skill_command(
        skills_dir: SkillsDirOption = None,
        tool_path: ToolPathOption = None,
        language: LanguageOption = SkillLanguage.AUTO,
        force: SkillForceOption = False,
    ) -> None:
        results = install_agent_skills(
            target=target,
            skills_dir=skills_dir,
            tool_path=tool_path,
            force=force,
            language=language,
        )
        for result in results:
            if result.installed:
                console.print(
                    f"installed {target.display_name} skill: {result.skill_path}",
                )
            else:
                console.print(
                    f"{target.display_name} skill already exists: {result.skill_path}",
                )

    def install_hooks_command(
        path: ProjectPathOption = None,
        tool_path: ToolPathOption = None,
        force: HookForceOption = False,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        result = install_agent_hooks(
            target=target,
            project_path=project_path,
            tool_path=tool_path,
            force=force,
        )
        console.print(f"installed {target.display_name} hooks: {result.hooks_path}")
        console.print(f"script: {result.script_path}")

    def uninstall_hooks_command(
        path: ProjectPathOption = None,
        is_global: Annotated[bool, typer.Option("-g", "--global", help="Uninstall global agent hooks.")] = False,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        uninstall_agent_hooks(target=target, project_path=project_path, is_global=is_global)
        loc_str = "global home" if is_global else str(project_path)
        console.print(f"[green]✓[/green] uninstalled {target.display_name} hooks ({loc_str})")

    def install_startup_hook_command(
        path: ProjectPathOption = None,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        result = install_startup_hook(target=target, project_path=project_path)
        console.print(f"[green]✓[/green] installed lightweight SessionStart awareness hook for {target.display_name}: {result.hooks_path}")

    _ = agent_app.command(
        "install-skill",
        help=f"Install the LLM Wiki {target.display_name} skills.",
    )(install_skill_command)
    _ = agent_app.command(
        "install-hooks",
        help=f"Install project-local {target.display_name} hooks for LLM Wiki.",
    )(install_hooks_command)
    _ = agent_app.command(
        "install-startup-hook",
        help=f"Install lightweight SessionStart awareness hook (~15 tokens once at startup).",
    )(install_startup_hook_command)
    _ = agent_app.command(
        "uninstall-hooks",
        help=f"Uninstall {target.display_name} hooks for LLM Wiki.",
    )(uninstall_hooks_command)


_register_install_commands(codex_app, CODEX_TARGET)
_register_install_commands(claude_app, CLAUDE_TARGET)
_register_install_commands(gemini_app, GEMINI_TARGET)


@app.command()
def add(
    path: Annotated[Path, typer.Argument(help="Markdown file to index.")],
    db: DbOption = None,
) -> None:
    """Index a Markdown document."""
    try:
        document = parse_markdown_file(path)
        document_id = upsert_document(resolve_db_path(db), document)
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"indexed {int(document_id)} {document.title} {document.path}")


def _print_search_results(query: str, db: Path | None, limit: int) -> None:
    try:
        results = search(resolve_db_path(db), query, limit)
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc
    if len(results) == 0:
        console.print("No results")
        return

    for result in results:
        tag_text = ", ".join(result.tags)
        console.print(f"{int(result.id)} | {result.title} | {result.path} | {tag_text}")
        console.print(f"  {result.snippet}")


@app.command("search")
def search_alias(
    query: Annotated[str, typer.Argument(help="Full-text query.")],
    db: DbOption = None,
    limit: LimitOption = DEFAULT_LIMIT,
) -> None:
    """Search indexed documents."""
    _print_search_results(query=query, db=db, limit=limit)


@app.command()
def show(
    document_id: Annotated[int, typer.Argument(help="Stored document id.")],
    db: DbOption = None,
) -> None:
    """Show a stored document by id."""
    try:
        document = get_document(resolve_db_path(db), DocumentId(document_id))
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc

    tag_text = ", ".join(document.tags)
    console.print(f"# {document.title}")
    console.print(f"id: {int(document.id)}")
    console.print(f"path: {document.path}")
    console.print(f"tags: {tag_text}")
    console.print("")
    console.print(document.body)


@app.command("ask-context")
def ask_context(
    query: Annotated[str, typer.Argument(help="Question or retrieval query.")],
    db: DbOption = None,
    limit: LimitOption = 3,
    min_score: Annotated[float, typer.Option(help="Minimum BM25 score threshold.")] = 0.0,
) -> None:
    """Print grounded snippets to paste into an LLM prompt."""
    try:
        results = search(resolve_db_path(db), query, limit, min_score=min_score)
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc
    if len(results) == 0:
        console.print("No context found")
        return

    console.print("Use this context before answering:")
    for result in results:
        console.print(f"- [{int(result.id)}] {result.title} ({result.path})")
        console.print(f"  {result.snippet}")


@app.command("doctor")
def doctor(
    path: ProjectPathOption = None,
) -> None:
    """Run diagnostics on Python, SQLite FTS5, project config, skills, and hooks."""
    run_doctor(path)


@app.command("hook-stats")
def hook_stats() -> None:
    """Report session hook performance and estimated token savings statistics."""
    show_hook_stats()


@app.command("watch")
def watch(
    path: ProjectPathOption = None,
    interval: Annotated[float, typer.Option(help="Poll interval in seconds.")] = 2.0,
) -> None:
    """Continuously watch markdown files and auto-reindex on change."""
    run_watcher(path, interval)


@git_hook_app.command("install")
def git_hook_install(
    path: ProjectPathOption = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing post-commit hook.")] = False,
) -> None:
    """Install a Git post-commit hook that automatically reindexes LLM Wiki."""
    try:
        install_git_hook(path, force=force)
    except ValueError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc
