"""Typer command surface for LLM Wiki."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from llm_wiki.codex import install_codex_skill
from llm_wiki.config import resolve_db_path
from llm_wiki.errors import WikiError
from llm_wiki.init_project import InitResult, initialize_global, initialize_project
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import DocumentId
from llm_wiki.store import get_document, search, upsert_document

DEFAULT_LIMIT = 5

app = typer.Typer(no_args_is_help=True)
codex_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
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


app.add_typer(codex_app, name="codex", help="Install Codex integrations.")
app.add_typer(project_app, name="project", help="Manage project-local wiki state.")


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


@codex_app.command("install-skill")
def codex_install_skill(
    skills_dir: SkillsDirOption = None,
    tool_path: ToolPathOption = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing LLM Wiki Codex skill."),
    ] = False,
) -> None:
    """Install the LLM Wiki recall skill for Codex."""
    result = install_codex_skill(
        skills_dir=skills_dir,
        tool_path=tool_path,
        force=force,
    )
    if result.installed:
        console.print(f"installed Codex skill: {result.skill_path}")
        return
    console.print(f"Codex skill already exists: {result.skill_path}")


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
) -> None:
    """Print grounded snippets to paste into an LLM prompt."""
    try:
        results = search(resolve_db_path(db), query, limit)
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
