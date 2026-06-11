"""Codex skill installation support."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

DEFAULT_CODEX_SKILLS_DIR: Final = Path("~/.agents/skills")
TOOL_REPO_PATH: Final = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """A generated Codex skill specification."""

    name: str
    description: str
    body_template: str


@dataclass(frozen=True, slots=True)
class SkillInstallResult:
    """Result of installing or preserving a Codex skill."""

    skill_name: str
    skill_path: Path
    installed: bool


SKILL_SPECS: Final[tuple[SkillSpec, ...]] = (
    SkillSpec(
        name="llm-wiki-init",
        description=(
            "Use this when a user wants to set up LLM Wiki globally or for a "
            "project, initialize wiki storage, create project-local AGENTS.md "
            "instructions, connect Codex to a project wiki, configure "
            '~/.llm-wiki, or says phrases like "LLM Wiki 붙여줘", '
            '"init wiki", "프로젝트에 위키 세팅", "공통 위키 세팅", or '
            '"Codex가 wiki 보게 해줘".'
        ),
        body_template="""# LLM Wiki Init

Use this skill to initialize either the global LLM Wiki home or a project wiki.
The goal is to leave future Codex sessions able to retrieve the correct durable
knowledge safely.

## Workflow

1. Identify whether the user wants global setup or project-local setup.
2. For global setup, run:

```bash
uv run --directory {tool_path} llm-wiki init
```

3. For project setup, run:

```bash
uv run --directory {tool_path} llm-wiki project init -p /path/to/project --agents
```

4. Verify the DB, config, docs folders, and any generated AGENTS.md exist.
5. Confirm AGENTS.md points at the target project `.llm-wiki/wiki.db`.

## Verification

Use `test -f` for generated files and grep AGENTS.md for `llm-wiki ask-context`,
`llm-wiki add`, and `--db /path/to/project/.llm-wiki/wiki.db`.

## Final Response

Report the initialized path, DB path, docs folders, and the recall command.
""",
    ),
    SkillSpec(
        name="llm-wiki-recall",
        description=(
            "Use this before project-specific or shared-context work when the "
            "user asks about previous decisions, project rules, runbooks, "
            'architecture, implementation context, "전에 어떻게 했지", '
            '"위키에서 찾아봐", "LLM Wiki 참고", or when a task depends on '
            "durable project knowledge."
        ),
        body_template="""# LLM Wiki Recall

Use this skill to retrieve durable project knowledge before answering or
changing code. Prefer approved LLM Wiki documents over chat memory when a
project has a local wiki.

## Workflow

1. Read the nearest applicable AGENTS.md from the target project.
2. Find an `llm-wiki ask-context` command and any explicit `--db` path.
3. If no explicit DB is present, inspect `.llm-wiki/config.toml`, then
   `LLM_WIKI_DB`, `LLM_WIKI_HOME`, and finally `~/.llm-wiki/wiki.db`.
4. Run:

```bash
uv run --directory {tool_path} llm-wiki ask-context "<question>" \\
  --db /path/to/project/.llm-wiki/wiki.db
```

5. Use returned context before answering or editing.

## Response Discipline

Say which Wiki source or title was used when available. Separate wiki-grounded
facts from inference, and say plainly when no context is found.
""",
    ),
    SkillSpec(
        name="llm-wiki-promote",
        description=(
            "Use this when stable knowledge from Agent Memory, a completed "
            "task, a decision, a runbook, or a repeated project explanation "
            "should be promoted into LLM Wiki."
        ),
        body_template="""# LLM Wiki Promote

Use this skill to turn a confirmed finding into durable Wiki knowledge. Promote
only stable decisions, runbooks, project conventions, source references, or
repeatable troubleshooting findings.

## Workflow

1. Choose the destination.
   - Project-specific knowledge: `/path/to/project/docs/decisions/`,
     `/path/to/project/docs/runbooks/`, or `/path/to/project/docs/references/`.
   - Global/common knowledge: `~/.llm-wiki/docs/decisions/`,
     `~/.llm-wiki/docs/runbooks/`, or `~/.llm-wiki/docs/references/`.
   - If `LLM_WIKI_HOME` is set, use `$LLM_WIKI_HOME/docs/` instead of
     `~/.llm-wiki/docs/`.
2. Write or update a Markdown document with frontmatter:

```markdown
---
title: Short Clear Title
tags: llm-wiki, project
---
```

3. Index it with the selected project DB:

```bash
uv run --directory {tool_path} llm-wiki add \\
  /path/to/project/docs/references/example.md \\
  --db /path/to/project/.llm-wiki/wiki.db
```

4. For global/common knowledge, index through global config resolution:

```bash
uv run --directory {tool_path} llm-wiki add \\
  ~/.llm-wiki/docs/references/example.md
```

5. Verify recall with `llm-wiki ask-context`. For global/common knowledge,
   omit `--db` unless `LLM_WIKI_DB` is intentionally set for a different DB.

## Final Response

Report the promoted file path, DB path, and verified recall query.
""",
    ),
    SkillSpec(
        name="llm-wiki-maintain",
        description=(
            "Use this when the user wants to audit, repair, reindex, clean up, "
            "or check freshness of an LLM Wiki project or global home."
        ),
        body_template="""# LLM Wiki Maintain

Use this skill to keep a project wiki reliable. Inspect first, reindex second,
and never delete user documents without explicit approval.

## Safe Audit

Check docs, AGENTS.md, project config, and global config:

```bash
find /path/to/project/docs -name '*.md' -type f
grep "llm-wiki ask-context" /path/to/project/AGENTS.md
test -f /path/to/project/.llm-wiki/config.toml
test -f ~/.llm-wiki/config.toml
```

## Reindex

For each Markdown file, run:

```bash
uv run --directory {tool_path} llm-wiki add /path/to/project/docs/<file>.md \\
  --db /path/to/project/.llm-wiki/wiki.db
```

Flag missing frontmatter, empty documents, stale names, or failed recall. Do not
delete DB files or user documents unless the user explicitly asks.

## Final Report

Report checked file count, reindexed file count, findings, recall verification,
and confirm no files were deleted.
""",
    ),
)


def install_codex_skill(
    skills_dir: Path | None,
    tool_path: Path | None,
    force: bool,
) -> tuple[SkillInstallResult, ...]:
    """Install all LLM Wiki Codex skills into a Codex skills directory."""
    resolved_skills_dir = _resolve_skills_dir(skills_dir)
    resolved_tool_path = TOOL_REPO_PATH if tool_path is None else tool_path
    return tuple(
        _install_skill(
            skills_dir=resolved_skills_dir,
            tool_path=resolved_tool_path.resolve(),
            spec=spec,
            force=force,
        )
        for spec in SKILL_SPECS
    )


def _install_skill(
    skills_dir: Path,
    tool_path: Path,
    spec: SkillSpec,
    force: bool,
) -> SkillInstallResult:
    skill_path = skills_dir / spec.name / "SKILL.md"
    if skill_path.exists() and not force:
        return SkillInstallResult(
            skill_name=spec.name,
            skill_path=skill_path,
            installed=False,
        )

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    _ = skill_path.write_text(_skill_text(spec, tool_path), encoding="utf-8")
    return SkillInstallResult(
        skill_name=spec.name,
        skill_path=skill_path,
        installed=True,
    )


def _resolve_skills_dir(skills_dir: Path | None) -> Path:
    if skills_dir is not None:
        return skills_dir.expanduser()
    return DEFAULT_CODEX_SKILLS_DIR.expanduser()


def _skill_text(spec: SkillSpec, tool_path: Path) -> str:
    body = spec.body_template.format(tool_path=tool_path)
    return f"""---
name: {spec.name}
description: {spec.description}
---

{body}
"""
