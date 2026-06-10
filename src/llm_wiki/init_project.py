"""Project initialization workflow for LLM Wiki."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from llm_wiki.config import resolve_home_path
from llm_wiki.store import initialize

PROJECT_CONFIG_TEXT: Final = """# LLM Wiki project configuration
docs_dir = "docs"
db_path = ".llm-wiki/wiki.db"
"""

GLOBAL_CONFIG_TEXT: Final = """# LLM Wiki global configuration
docs_dir = "docs"
db_path = "wiki.db"
"""

INDEX_TEXT: Final = """---
title: LLM Wiki Index
tags: index, llm-wiki
---

# LLM Wiki Index

Use this page as the entry point for durable project knowledge.

## Sections

- `decisions/`: approved architecture and product decisions
- `runbooks/`: repeatable operating procedures
- `references/`: stable source notes and external references
"""

TOOL_REPO_PATH: Final = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class InitResult:
    """Files and directories prepared for a project wiki."""

    project_path: Path
    db_path: Path
    config_path: Path
    index_path: Path
    agents_path: Path | None
    scope: str


def initialize_project(project_path: Path, include_agents: bool) -> InitResult:
    """Create a project-local LLM Wiki layout."""
    project_path.mkdir(parents=True, exist_ok=True)
    wiki_dir = project_path / ".llm-wiki"
    docs_dir = project_path / "docs"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    for child_name in ("decisions", "runbooks", "references"):
        (docs_dir / child_name).mkdir(parents=True, exist_ok=True)

    db_path = wiki_dir / "wiki.db"
    initialize(db_path)

    config_path = wiki_dir / "config.toml"
    _write_if_missing(config_path, PROJECT_CONFIG_TEXT)

    index_path = docs_dir / "index.md"
    _write_if_missing(index_path, INDEX_TEXT)

    agents_path = project_path / "AGENTS.md" if include_agents else None
    if agents_path is not None:
        _write_or_append_agents(
            agents_path,
            _agents_text(project_path=project_path, tool_path=TOOL_REPO_PATH),
        )

    return InitResult(
        project_path=project_path,
        db_path=db_path,
        config_path=config_path,
        index_path=index_path,
        agents_path=agents_path,
        scope="project",
    )


def initialize_global(home_path: Path | None) -> InitResult:
    """Create the global LLM Wiki layout."""
    resolved_home = resolve_home_path(home_path)
    docs_dir = resolved_home / "docs"
    resolved_home.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    for child_name in ("decisions", "runbooks", "references"):
        (docs_dir / child_name).mkdir(parents=True, exist_ok=True)

    db_path = resolved_home / "wiki.db"
    initialize(db_path)

    config_path = resolved_home / "config.toml"
    _write_if_missing(config_path, GLOBAL_CONFIG_TEXT)

    index_path = docs_dir / "index.md"
    _write_if_missing(index_path, INDEX_TEXT)

    return InitResult(
        project_path=resolved_home,
        db_path=db_path,
        config_path=config_path,
        index_path=index_path,
        agents_path=None,
        scope="global",
    )


def _write_if_missing(path: Path, text: str) -> None:
    if path.exists():
        return
    _ = path.write_text(text, encoding="utf-8")


def _write_or_append_agents(path: Path, text: str) -> None:
    if not path.exists():
        _ = path.write_text(text, encoding="utf-8")
        return

    current = path.read_text(encoding="utf-8")
    if "LLM Wiki Instructions" in current:
        return

    separator = "\n\n" if current.endswith("\n") else "\n\n\n"
    _ = path.write_text(f"{current}{separator}{text}", encoding="utf-8")


def _agents_text(project_path: Path, tool_path: Path) -> str:
    project_root = project_path.resolve()
    wiki_db = project_root / ".llm-wiki" / "wiki.db"
    docs_file = project_root / "docs" / "<file>.md"
    return f"""# LLM Wiki Instructions

Before answering project-specific questions or changing behavior, retrieve
durable project knowledge with:

```bash
uv run --directory {tool_path} llm-wiki ask-context "<question>" --db {wiki_db}
```

When a new long-lived rule, decision, runbook, or reference becomes approved,
write it as Markdown under `{project_root}/docs/` and index it with:

```bash
uv run --directory {tool_path} llm-wiki add {docs_file} --db {wiki_db}
```

Use Agent Memory for working observations and session recall. Promote only
stable, reviewed knowledge into LLM Wiki so future Codex sessions can cite the
same source-grounded context.
"""
