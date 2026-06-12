"""Codex hook installation support."""

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Final

TOOL_REPO_PATH: Final = Path(__file__).resolve().parents[2]
HOOK_SCRIPT_NAME: Final = "llm_wiki_user_prompt.py"

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


@dataclass(frozen=True, slots=True)
class HookInstallResult:
    """Result of installing Codex hook files."""

    hooks_path: Path
    script_path: Path


def install_codex_hooks(
    project_path: Path,
    tool_path: Path | None,
    force: bool,
) -> HookInstallResult:
    """Install project-local Codex hooks for LLM Wiki recall."""
    resolved_project_path = project_path.expanduser().resolve()
    resolved_tool_path = TOOL_REPO_PATH if tool_path is None else tool_path
    codex_dir = resolved_project_path / ".codex"
    hooks_dir = codex_dir / "hooks"
    hooks_path = codex_dir / "hooks.json"
    script_path = hooks_dir / HOOK_SCRIPT_NAME

    hooks_dir.mkdir(parents=True, exist_ok=True)
    if force or not script_path.exists():
        _ = script_path.write_text(
            _hook_script(resolved_tool_path.resolve()),
            encoding="utf-8",
        )
        script_path.chmod(0o755)

    hooks_data = _load_hooks_json(hooks_path)
    _merge_user_prompt_hook(hooks_data, script_path)
    _ = hooks_path.write_text(
        json.dumps(hooks_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return HookInstallResult(hooks_path=hooks_path, script_path=script_path)


def _load_hooks_json(hooks_path: Path) -> dict[str, JsonValue]:
    if not hooks_path.exists():
        return {"hooks": {}}

    loaded: JsonValue = json.loads(hooks_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return {"hooks": {}}

    data = dict(loaded)
    if not isinstance(data.get("hooks"), dict):
        data["hooks"] = {}
    return data


def _merge_user_prompt_hook(
    hooks_data: dict[str, JsonValue],
    script_path: Path,
) -> None:
    hooks_value = hooks_data.get("hooks")
    if not isinstance(hooks_value, dict):
        hooks_value = {}
        hooks_data["hooks"] = hooks_value

    event_value = hooks_value.get("UserPromptSubmit")
    if not isinstance(event_value, list):
        event_value = []
        hooks_value["UserPromptSubmit"] = event_value

    command = f"python3 {shlex.quote(str(script_path))}"
    if _has_llm_wiki_hook(event_value, command):
        return
    event_value.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": 5,
                    "statusMessage": "Loading LLM Wiki context",
                },
            ],
        },
    )


def _has_llm_wiki_hook(event_value: list[JsonValue], command: str) -> bool:
    for group in event_value:
        if not isinstance(group, dict):
            continue
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if isinstance(hook, dict) and hook.get("command") == command:
                return True
    return False


def _hook_script(tool_path: Path) -> str:
    tool_path_text = str(tool_path)
    return f"""#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

TOOL_PATH = {tool_path_text!r}
MAX_CONTEXT_CHARS = 6000
COMMAND_LABEL = "llm-wiki ask-context"


def main():
    event = json.load(sys.stdin)
    prompt = event.get("prompt", "")
    cwd_text = event.get("cwd") or os.getcwd()
    if not isinstance(prompt, str) or not prompt.strip():
        return
    if not isinstance(cwd_text, str):
        return

    cwd = Path(cwd_text)
    if not should_query_wiki(cwd):
        return

    context = ask_context(prompt, cwd)
    if not context or context.strip() == "No context found":
        return

    context = context[:MAX_CONTEXT_CHARS]
    print(json.dumps({{
        "hookSpecificOutput": {{
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "LLM Wiki context from " + COMMAND_LABEL + ":\\n" + context
            ),
        }}
    }}, ensure_ascii=False))


def should_query_wiki(cwd):
    if os.environ.get("LLM_WIKI_DB") or os.environ.get("LLM_WIKI_HOME"):
        return True
    for path in (cwd, *cwd.parents):
        if (path / ".llm-wiki" / "config.toml").is_file():
            return True
    return False


def ask_context(prompt, cwd):
    command = ["llm-wiki", "ask-context", prompt]
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=4,
            check=False,
        )
    except FileNotFoundError:
        result = subprocess.run(
            ["uv", "run", "--directory", TOOL_PATH, *command],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=4,
            check=False,
        )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


if __name__ == "__main__":
    main()
"""
