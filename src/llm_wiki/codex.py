"""Codex skill installation support."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

SKILL_NAME: Final = "llm-wiki-recall"
DEFAULT_CODEX_SKILLS_DIR: Final = Path("~/.agents/skills")
TOOL_REPO_PATH: Final = Path(__file__).resolve().parents[2]
SKILL_DESCRIPTION: Final = (
    "Use this before project-specific or shared-context work when the user asks "
    "about previous decisions, project rules, runbooks, architecture, "
    'implementation context, "전에 어떻게 했지", "위키에서 찾아봐", '
    '"LLM Wiki 참고", or when a task depends on durable project knowledge. '
    "This skill reads project AGENTS.md/config/env to find the right LLM Wiki "
    "DB, runs ask-context, and separates wiki-grounded facts from inference."
)


@dataclass(frozen=True, slots=True)
class SkillInstallResult:
    """Result of installing or preserving a Codex skill."""

    skill_path: Path
    installed: bool


def install_codex_skill(
    skills_dir: Path | None,
    tool_path: Path | None,
    force: bool,
) -> SkillInstallResult:
    """Install the LLM Wiki recall skill into a Codex skills directory."""
    resolved_skills_dir = _resolve_skills_dir(skills_dir)
    skill_path = resolved_skills_dir / SKILL_NAME / "SKILL.md"
    if skill_path.exists() and not force:
        return SkillInstallResult(skill_path=skill_path, installed=False)

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_tool_path = TOOL_REPO_PATH if tool_path is None else tool_path
    _ = skill_path.write_text(
        _skill_text(resolved_tool_path.resolve()),
        encoding="utf-8",
    )
    return SkillInstallResult(skill_path=skill_path, installed=True)


def _resolve_skills_dir(skills_dir: Path | None) -> Path:
    if skills_dir is not None:
        return skills_dir.expanduser()
    return DEFAULT_CODEX_SKILLS_DIR.expanduser()


def _skill_text(tool_path: Path) -> str:
    return f"""---
name: llm-wiki-recall
description: {SKILL_DESCRIPTION}
---

# LLM Wiki Recall

Use this skill to retrieve durable project knowledge before answering or
changing code. Prefer approved LLM Wiki documents over chat memory when a
project has a local wiki.

## Workflow

1. Read the nearest applicable `AGENTS.md` from the target project.
2. Look for an `llm-wiki ask-context` command and any explicit `--db` path.
3. If no explicit `--db` is present, inspect `.llm-wiki/config.toml`, then
   `LLM_WIKI_DB`, then `LLM_WIKI_HOME`, then `~/.llm-wiki/wiki.db`.
4. Run `llm-wiki ask-context "<question>"` with the best project-specific DB.
5. If `llm-wiki` is not on PATH, use this checkout-based fallback:

```bash
uv run --directory {tool_path} llm-wiki ask-context "<question>" \\
  --db /path/to/project/.llm-wiki/wiki.db
```

6. Use returned context before answering or editing. If there is no context,
   say that plainly and continue from inspected files.

## Response Discipline

- Say which Wiki source or title was used when the output shows one.
- Separate wiki-grounded facts from your inference when you add reasoning.
- Do not present Agent Memory observations as approved Wiki knowledge.
- If the wiki is not initialized, suggest `llm-wiki project init -p <project> --agents`.

## Verification

For a project wiki, verify:

```bash
llm-wiki ask-context "<question>" --db /path/to/project/.llm-wiki/wiki.db
```

The output should include `Use this context before answering:` or
`No context found`.
"""
