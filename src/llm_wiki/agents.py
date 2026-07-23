"""Agent CLI targets for LLM Wiki skill and hook installation."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

TOOL_REPO_PATH: Final = Path(__file__).resolve().parents[2]
HOOK_SCRIPT_NAME: Final = "llm_wiki_user_prompt.py"


class AgentKind(StrEnum):
    """Supported agent CLIs."""

    CODEX = "codex"
    CLAUDE = "claude"
    GEMINI = "gemini"


@dataclass(frozen=True, slots=True)
class AgentTarget:
    """Installation target describing one agent CLI."""

    kind: AgentKind
    display_name: str
    default_skills_dir: Path
    hook_dir_name: str
    hook_config_name: str
    hook_event: str
    hook_output_includes_event: bool
    hook_trust_text: str
    hook_choice_text: str

    @property
    def install_hooks_command(self) -> str:
        """CLI invocation that installs this target's project hooks."""
        return f"llm-wiki {self.kind} install-hooks"

    @property
    def hook_config_rel(self) -> str:
        """Hook configuration file path relative to the project root."""
        return f"{self.hook_dir_name}/{self.hook_config_name}"

    @property
    def hook_script_rel(self) -> str:
        """Hook script path relative to the project root."""
        return f"{self.hook_dir_name}/hooks/{HOOK_SCRIPT_NAME}"


CODEX_TARGET: Final = AgentTarget(
    kind=AgentKind.CODEX,
    display_name="Codex",
    default_skills_dir=Path("~/.agents/skills"),
    hook_dir_name=".codex",
    hook_config_name="hooks.json",
    hook_event="UserPromptSubmit",
    hook_output_includes_event=True,
    hook_trust_text=(
        "Tell the user to open Codex `/hooks`, review the new project hook, and "
        "trust\n   it before expecting automatic execution."
    ),
    hook_choice_text="""\
- `UserPromptSubmit` is the default because it runs right before the user prompt
  is sent and can add model-visible Wiki context.
- `SessionStart` is acceptable later for light startup guidance, such as saying
  that the project has LLM Wiki configured. Do not use it for full recall search.
- `PreToolUse` and `PostToolUse` are better for command/file guardrails, not
  normal Wiki retrieval.
- Do not use `Stop` or `PostCompact` to auto-promote content into Wiki. Promotion
  should stay explicit through `llm-wiki-promote`.""",
)

CLAUDE_TARGET: Final = AgentTarget(
    kind=AgentKind.CLAUDE,
    display_name="Claude Code",
    default_skills_dir=Path("~/.claude/skills"),
    hook_dir_name=".claude",
    hook_config_name="settings.json",
    hook_event="UserPromptSubmit",
    hook_output_includes_event=True,
    hook_trust_text=(
        "Tell the user to open `/hooks` in Claude Code and review the new project\n"
        "   hook. Hook changes made outside Claude Code require review there "
        "before\n   they run."
    ),
    hook_choice_text="""\
- `UserPromptSubmit` is the default because it runs right before the user prompt
  is sent and can add model-visible Wiki context.
- `SessionStart` is acceptable later for light startup guidance, such as saying
  that the project has LLM Wiki configured. Do not use it for full recall search.
- `PreToolUse` and `PostToolUse` are better for command/file guardrails, not
  normal Wiki retrieval.
- Do not use `Stop` or `PreCompact` to auto-promote content into Wiki. Promotion
  should stay explicit through `llm-wiki-promote`.""",
)

GEMINI_TARGET: Final = AgentTarget(
    kind=AgentKind.GEMINI,
    display_name="Gemini CLI",
    default_skills_dir=Path("~/.gemini/skills"),
    hook_dir_name=".gemini",
    hook_config_name="settings.json",
    hook_event="BeforeAgent",
    hook_output_includes_event=False,
    hook_trust_text=(
        "Tell the user to restart Gemini CLI so `.gemini/settings.json` is "
        "reloaded\n   and to trust the project folder when prompted."
    ),
    hook_choice_text="""\
- `BeforeAgent` is the default because it runs right before the agent handles
  the submitted prompt and can add model-visible Wiki context.
- `SessionStart` is acceptable later for light startup guidance, such as saying
  that the project has LLM Wiki configured. Do not use it for full recall search.
- `BeforeTool` and `AfterTool` are better for command/file guardrails, not
  normal Wiki retrieval.
- Do not use `AfterAgent` or `SessionEnd` to auto-promote content into Wiki.
  Promotion should stay explicit through `llm-wiki-promote`.""",
)

ALL_TARGETS: Final = (CODEX_TARGET, CLAUDE_TARGET, GEMINI_TARGET)
