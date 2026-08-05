"""Typer command surface for LLM Wiki."""

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from llm_wiki.agent_hooks import (
    install_agent_hooks,
    install_guardrail_hook,
    install_startup_hook,
    uninstall_agent_hooks,
)
from llm_wiki.agent_skills import (
    SkillInstallResult,
    SkillLanguage,
    install_agent_skills,
    uninstall_agent_skills,
)
from llm_wiki.agents import CLAUDE_TARGET, CODEX_TARGET, GEMINI_TARGET, AgentTarget
from llm_wiki.config import resolve_db_path
from llm_wiki.doctor import run_doctor
from llm_wiki.errors import WikiError
from llm_wiki.git_hook import install_git_hook
from llm_wiki.hook_stats import show_hook_stats
from llm_wiki.init_project import InitResult, initialize_global, initialize_project
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import DocumentId, EmbedResult
from llm_wiki.retrieval import build_semantic_search, refresh_embeddings
from llm_wiki.store import (
    backlinks,
    get_document,
    outgoing_links,
    record_retrieval,
    reindex_directory,
    search,
    upsert_document,
    usage_report,
)
from llm_wiki.watcher import run_watcher

DEFAULT_LIMIT = 5
DEFAULT_USAGE_WEIGHT = 0.3

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


def _print_skill_installs(
    target: AgentTarget,
    results: Sequence[SkillInstallResult],
) -> None:
    for result in results:
        if result.installed:
            console.print(
                f"[green]✓[/green] installed {target.display_name} "
                f"skill: {result.skill_path}",
            )
        else:
            console.print(
                f"{target.display_name} skill already exists: {result.skill_path}",
            )


def _print_skill_removals(target: AgentTarget, removed: Sequence[Path]) -> None:
    if not removed:
        console.print(f"No {target.display_name} skills found to uninstall.")
        return
    for item in removed:
        console.print(
            f"[green]✓[/green] uninstalled {target.display_name} skill: {item}"
        )


def _register_install_commands(agent_app: typer.Typer, target: AgentTarget) -> None:
    def install_skill_command(
        path: ProjectPathOption = None,
        skills_dir: SkillsDirOption = None,
        tool_path: ToolPathOption = None,
        language: LanguageOption = SkillLanguage.AUTO,
        force: SkillForceOption = False,
        is_global: Annotated[
            bool,
            typer.Option(
                "-g",
                "--global",
                help="Install global agent skills into home directory.",
            ),
        ] = False,
    ) -> None:
        project_path = None if (is_global or path is None) else path
        results = install_agent_skills(
            target=target,
            skills_dir=skills_dir,
            project_path=project_path,
            tool_path=tool_path,
            force=force,
            language=language,
        )
        _print_skill_installs(target, results)

    def uninstall_skill_command(
        path: ProjectPathOption = None,
        skills_dir: SkillsDirOption = None,
        is_global: Annotated[
            bool,
            typer.Option(
                "-g",
                "--global",
                help="Uninstall global agent skills from home directory.",
            ),
        ] = False,
    ) -> None:
        project_path = None if (is_global or path is None) else path
        removed = uninstall_agent_skills(
            target=target,
            skills_dir=skills_dir,
            project_path=project_path,
            is_global=is_global,
        )
        _print_skill_removals(target, removed)

    def install_hooks_command(
        path: ProjectPathOption = None,
        tool_path: ToolPathOption = None,
        force: HookForceOption = False,
        auto_prompt: Annotated[
            bool,
            typer.Option(
                "--auto-prompt",
                help=(
                    "Also auto-inject wiki context on every user prompt "
                    "(higher token usage)."
                ),
            ),
        ] = False,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        result = install_agent_hooks(
            target=target,
            project_path=project_path,
            tool_path=tool_path,
            force=force,
            include_prompt_auto_inject=auto_prompt,
        )
        console.print(
            f"[green]✓[/green] installed complete smart hook suite for "
            f"{target.display_name}: {result.hooks_path}"
        )
        console.print("  - SessionStart awareness hook (~15 tokens once at startup)")
        console.print("  - PreToolUse guardrail hook for sensitive file edits")

    def uninstall_hooks_command(
        path: ProjectPathOption = None,
        is_global: Annotated[
            bool, typer.Option("-g", "--global", help="Uninstall global agent hooks.")
        ] = False,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        _ = uninstall_agent_hooks(
            target=target, project_path=project_path, is_global=is_global
        )
        loc_str = "global home" if is_global else str(project_path)
        console.print(
            f"[green]✓[/green] uninstalled {target.display_name} hooks ({loc_str})"
        )

    def install_startup_hook_command(
        path: ProjectPathOption = None,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        result = install_startup_hook(target=target, project_path=project_path)
        console.print(
            f"[green]✓[/green] installed lightweight SessionStart awareness hook "
            f"for {target.display_name}: {result.hooks_path}"
        )

    def install_guardrail_hook_command(
        path: ProjectPathOption = None,
    ) -> None:
        project_path = Path.cwd() if path is None else path
        result = install_guardrail_hook(target=target, project_path=project_path)
        console.print(
            f"[green]✓[/green] installed selective PreToolUse guardrail hook "
            f"for {target.display_name}: {result.hooks_path}"
        )

    _ = agent_app.command(
        "install-skill",
        help=(
            f"Install the LLM Wiki {target.display_name} skills "
            "(globally or for a project)."
        ),
    )(install_skill_command)
    _ = agent_app.command(
        "uninstall-skill",
        help=(
            f"Uninstall the LLM Wiki {target.display_name} skills "
            "(globally or from a project)."
        ),
    )(uninstall_skill_command)
    _ = agent_app.command(
        "install-hooks",
        help=f"Install project-local {target.display_name} hooks for LLM Wiki.",
    )(install_hooks_command)
    _ = agent_app.command(
        "install-startup-hook",
        help=(
            "Install lightweight SessionStart awareness hook "
            "(~15 tokens once at startup)."
        ),
    )(install_startup_hook_command)
    _ = agent_app.command(
        "install-guardrail-hook",
        help="Install selective PreToolUse guardrail hook for sensitive file edits.",
    )(install_guardrail_hook_command)
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


@app.command("reindex")
def reindex(
    path: ProjectPathOption = None,
    db: DbOption = None,
) -> None:
    """Reindex every Markdown document under a project directory."""
    root = (path or Path.cwd()).expanduser().resolve()
    if not root.is_dir():
        console.print(f"Error: Not a directory: {root}")
        raise typer.Exit(1)

    try:
        result = reindex_directory(resolve_db_path(db), root)
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"indexed {result.indexed} removed {result.removed}")
    _print_embed_result(refresh_embeddings(resolve_db_path(db)))
    for failure in result.failures:
        console.print(f"failed {failure.path} | {failure.reason}")
    if len(result.failures) > 0:
        raise typer.Exit(1)


def _print_embed_result(result: EmbedResult | None) -> None:
    """Report an embedding pass, staying silent when embedding is off."""
    if result is None:
        return
    console.print(f"embedded {result.embedded} reused {result.reused}")
    if result.reason is not None:
        # Not an exit code: the documents are indexed and searchable by BM25,
        # and the vectors catch up on the next run.
        console.print(
            f"embedding incomplete ({result.failed} pending) | {result.reason}"
        )


@app.command("embed")
def embed(
    db: DbOption = None,
) -> None:
    """Embed every indexed chunk that has no vector for the configured model."""
    result = refresh_embeddings(resolve_db_path(db))
    if result is None:
        console.print("Embedding is not configured (see `llm-wiki doctor`)")
        return
    _print_embed_result(result)


TagOption = Annotated[
    list[str] | None,
    typer.Option(
        "--tag",
        help="Scope to documents with this tag (repeatable; all must match). "
        "Use e.g. project:foo to partition one shared wiki.",
    ),
]


def _print_search_results(
    query: str, db: Path | None, limit: int, tags: list[str] | None
) -> None:
    try:
        db_path = resolve_db_path(db)
        results = search(
            db_path,
            query,
            limit,
            tags=tags or (),
            semantic=build_semantic_search(db_path, query),
        )
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
    tag: TagOption = None,
) -> None:
    """Search indexed documents."""
    _print_search_results(query=query, db=db, limit=limit, tags=tag)


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


@app.command("links")
def links(
    document_id: Annotated[int, typer.Argument(help="Stored document id.")],
    db: DbOption = None,
) -> None:
    """Show outgoing wikilinks and backlinks for a document."""
    db_path = resolve_db_path(db)
    try:
        document = get_document(db_path, DocumentId(document_id))
        outgoing = outgoing_links(db_path, DocumentId(document_id))
        incoming = backlinks(db_path, DocumentId(document_id))
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"# {document.title}")
    console.print(f"→ outgoing ({len(outgoing)}):")
    for link in outgoing:
        console.print(f"  [{int(link.id)}] {link.title} | {link.path}")
    console.print(f"← backlinks ({len(incoming)}):")
    for link in incoming:
        console.print(f"  [{int(link.id)}] {link.title} | {link.path}")


@app.command("ask-context")
def ask_context(
    query: Annotated[str, typer.Argument(help="Question or retrieval query.")],
    db: DbOption = None,
    limit: LimitOption = 3,
    min_score: Annotated[
        float, typer.Option(help="Minimum BM25 score threshold.")
    ] = 0.0,
    usage_weight: Annotated[
        float,
        typer.Option(
            "--usage-weight",
            min=0.0,
            help="Promote documents that were retrieved before (0 disables).",
        ),
    ] = DEFAULT_USAGE_WEIGHT,
    tag: TagOption = None,
) -> None:
    """Print grounded snippets to paste into an LLM prompt."""
    db_path = resolve_db_path(db)
    try:
        results = search(
            db_path,
            query,
            limit,
            min_score=min_score,
            usage_weight=usage_weight,
            tags=tag or (),
            semantic=build_semantic_search(db_path, query),
        )
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc
    if len(results) == 0:
        console.print("No context found")
        return

    # Grounding is the signal worth ranking on, so only ask-context records it.
    record_retrieval(db_path, [result.id for result in results])

    console.print("Use this context before answering:")
    for result in results:
        console.print(f"- [{int(result.id)}] {result.title} ({result.path})")
        console.print(f"  {result.snippet}")


@app.command("usage")
def usage(
    db: DbOption = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, help="Maximum retrieved documents to list."),
    ] = 20,
) -> None:
    """Report how often each document has been retrieved for grounding."""
    try:
        report = usage_report(resolve_db_path(db))
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc
    if len(report) == 0:
        console.print("No documents indexed")
        return

    retrieved = [item for item in report if item.retrieved_count > 0]
    never = [item for item in report if item.retrieved_count == 0]

    for item in retrieved[:limit]:
        last_seen = item.last_retrieved_at or "-"
        console.print(
            f"{item.retrieved_count} | {item.title} | {item.path} | {last_seen}"
        )
    console.print(f"documents: {len(report)} | never retrieved: {len(never)}")
    for item in never[:limit]:
        console.print(f"  0 | {item.title} | {item.path}")


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
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing post-commit hook.")
    ] = False,
) -> None:
    """Install a Git post-commit hook that automatically reindexes LLM Wiki."""
    try:
        _ = install_git_hook(path, force=force)
    except WikiError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(1) from exc
