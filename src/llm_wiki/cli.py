"""Typer command surface for LLM Wiki."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from llm_wiki.config import resolve_db_path
from llm_wiki.errors import WikiError
from llm_wiki.init_project import initialize_global, initialize_project
from llm_wiki.markdown import parse_markdown_file
from llm_wiki.models import DocumentId
from llm_wiki.store import get_document, search, upsert_document

DEFAULT_LIMIT = 5

app = typer.Typer(no_args_is_help=True)
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
ProjectOption = Annotated[
    Path | None,
    typer.Option(
        "--project",
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


@app.command()
def init(
    project: ProjectOption = None,
    global_wiki: Annotated[
        bool,
        typer.Option(
            "--global",
            help="Initialize the global LLM Wiki home.",
        ),
    ] = False,
    home: HomeOption = None,
    agents: Annotated[
        bool,
        typer.Option(
            "--agents",
            help="Write AGENTS.md instructions for Codex integration.",
        ),
    ] = False,
) -> None:
    """Initialize an LLM Wiki layout for a project."""
    if global_wiki:
        result = initialize_global(home)
    else:
        project_path = Path.cwd() if project is None else project
        result = initialize_project(project_path, include_agents=agents)
    console.print(f"initialized {result.scope} {result.project_path}")
    console.print(f"db: {result.db_path}")
    console.print(f"config: {result.config_path}")
    console.print(f"index: {result.index_path}")
    if result.agents_path is not None:
        console.print(f"agents: {result.agents_path}")


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


@app.command()
def search_command(
    query: Annotated[str, typer.Argument(help="Full-text query.")],
    db: DbOption = None,
    limit: LimitOption = DEFAULT_LIMIT,
) -> None:
    """Search indexed documents."""
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
    search_command(query=query, db=db, limit=limit)


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
