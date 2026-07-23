"""Agent hook installation support."""

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from llm_wiki.agents import HOOK_SCRIPT_NAME, TOOL_REPO_PATH, AgentKind, AgentTarget

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


@dataclass(frozen=True, slots=True)
class HookInstallResult:
    """Result of installing agent hook files."""

    hooks_path: Path
    script_path: Path


def install_agent_hooks(
    target: AgentTarget,
    project_path: Path,
    tool_path: Path | None,
    force: bool,
) -> HookInstallResult:
    """Install project-local agent hooks for LLM Wiki recall."""
    resolved_project_path = project_path.expanduser().resolve()
    resolved_tool_path = TOOL_REPO_PATH if tool_path is None else tool_path
    config_dir = resolved_project_path / target.hook_dir_name
    hooks_dir = config_dir / "hooks"
    hooks_path = config_dir / target.hook_config_name
    script_path = hooks_dir / HOOK_SCRIPT_NAME

    hooks_dir.mkdir(parents=True, exist_ok=True)
    if force or not script_path.exists():
        _ = script_path.write_text(
            _hook_script(target, resolved_tool_path.resolve()),
            encoding="utf-8",
        )
        script_path.chmod(0o755)

    hooks_data = _load_hooks_json(hooks_path)
    _merge_hook(hooks_data, target, script_path)
    _ = hooks_path.write_text(
        json.dumps(hooks_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return HookInstallResult(hooks_path=hooks_path, script_path=script_path)


def uninstall_agent_hooks(
    target: AgentTarget,
    project_path: Path | None = None,
    is_global: bool = False,
) -> bool:
    """Uninstall agent hooks for LLM Wiki recall (project-local or global)."""
    if is_global:
        config_dir = Path(f"~/{target.hook_dir_name}").expanduser().resolve()
    else:
        resolved_project_path = (project_path or Path.cwd()).expanduser().resolve()
        config_dir = resolved_project_path / target.hook_dir_name

    hooks_path = config_dir / target.hook_config_name
    script_path = config_dir / "hooks" / HOOK_SCRIPT_NAME

    if script_path.exists():
        script_path.unlink()

    if hooks_path.exists():
        hooks_data = _load_hooks_json(hooks_path)
        _remove_hook(hooks_data, target, script_path)
        hooks_path.write_text(
            json.dumps(hooks_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # Also clean up global hook if uninstalling
    global_config_dir = Path(f"~/{target.hook_dir_name}").expanduser().resolve()
    if global_config_dir != config_dir:
        global_hooks_path = global_config_dir / target.hook_config_name
        global_script_path = global_config_dir / "hooks" / HOOK_SCRIPT_NAME
        if global_script_path.exists():
            global_script_path.unlink()
        if global_hooks_path.exists():
            global_data = _load_hooks_json(global_hooks_path)
            _remove_hook(global_data, target, global_script_path)
            global_hooks_path.write_text(
                json.dumps(global_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return True


def _remove_hook(
    hooks_data: dict[str, JsonValue],
    target: AgentTarget,
    script_path: Path,
) -> None:
    hooks_value = hooks_data.get("hooks")
    if not isinstance(hooks_value, dict):
        return

    event_value = hooks_value.get(target.hook_event)
    if not isinstance(event_value, list):
        return

    script_name = HOOK_SCRIPT_NAME
    new_event_value = []
    for group in event_value:
        if not isinstance(group, dict):
            new_event_value.append(group)
            continue
        hooks = group.get("hooks")
        if not isinstance(hooks, list):
            new_event_value.append(group)
            continue
        filtered_hooks = [
            h for h in hooks
            if not (isinstance(h, dict) and script_name in str(h.get("command", "")))
        ]
        if filtered_hooks:
            group["hooks"] = filtered_hooks
            new_event_value.append(group)

    hooks_value[target.hook_event] = new_event_value


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


def _merge_hook(
    hooks_data: dict[str, JsonValue],
    target: AgentTarget,
    script_path: Path,
) -> None:
    hooks_value = hooks_data.get("hooks")
    if not isinstance(hooks_value, dict):
        hooks_value = {}
        hooks_data["hooks"] = hooks_value

    event_value = hooks_value.get(target.hook_event)
    if not isinstance(event_value, list):
        event_value = []
        hooks_value[target.hook_event] = event_value

    command = f"python3 {shlex.quote(str(script_path))}"
    if _has_llm_wiki_hook(event_value, command):
        return
    event_value.append({"hooks": [_hook_entry(target, command)]})


def _hook_entry(target: AgentTarget, command: str) -> dict[str, JsonValue]:
    match target.kind:
        case AgentKind.CODEX:
            return {
                "type": "command",
                "command": command,
                "timeout": 5,
                "statusMessage": "Loading LLM Wiki context",
            }
        case AgentKind.CLAUDE:
            return {
                "type": "command",
                "command": command,
                "timeout": 5,
            }
        case AgentKind.GEMINI:
            return {
                "type": "command",
                "name": "llm-wiki-context",
                "command": command,
                "timeout": 5000,
                "description": "Loading LLM Wiki context",
            }


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


def _hook_output_source(target: AgentTarget) -> str:
    if target.hook_output_includes_event:
        return (
            '{"hookEventName": '
            + json.dumps(target.hook_event)
            + ', "additionalContext": context_text}'
        )
    return '{"additionalContext": context_text}'


def _hook_script(target: AgentTarget, tool_path: Path) -> str:
    tool_path_text = str(tool_path)
    hook_output_source = _hook_output_source(target)
    return f"""#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOL_PATH = {tool_path_text!r}
MAX_CONTEXT_CHARS = int(os.environ.get("LLM_WIKI_MAX_CONTEXT_CHARS", 2000))
MIN_CONTEXT_CHARS = int(os.environ.get("LLM_WIKI_MIN_CONTEXT_CHARS", 100))
MIN_PROMPT_CHARS = int(os.environ.get("LLM_WIKI_MIN_PROMPT_CHARS", 3))
SESSION_TTL = int(os.environ.get("LLM_WIKI_SESSION_TTL", 1800))
COMMAND_LABEL = "llm-wiki ask-context"


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return

    if not isinstance(event, dict):
        return

    prompt = event.get("prompt", "")
    cwd_text = event.get("cwd") or os.getcwd()
    session_id = event.get("session_id") or event.get("sessionId") or ""

    if not isinstance(prompt, str) or len(prompt.strip()) < MIN_PROMPT_CHARS:
        return
    if not isinstance(cwd_text, str):
        return

    cwd = Path(cwd_text)
    if not should_query_wiki(cwd):
        return

    context = ask_context(prompt, cwd)
    if not context or context.strip() == "No context found":
        return

    clean_body = strip_context_header(context)
    if len(clean_body) < MIN_CONTEXT_CHARS:
        return

    context = truncate_context(context, MAX_CONTEXT_CHARS)
    if not context.strip():
        return

    context_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()
    db_mtime = get_db_mtime(cwd)
    if is_duplicate_context(session_id, cwd, context_hash, db_mtime):
        return

    save_context_hash(session_id, cwd, context_hash, db_mtime, len(context))

    context_text = "LLM Wiki context from " + COMMAND_LABEL + ":\\n" + context
    print(json.dumps(
        {{"hookSpecificOutput": {hook_output_source}}},
        ensure_ascii=False,
    ))


def strip_context_header(context):
    lines = context.strip().splitlines()
    if lines and lines[0].startswith("Use this context before answering"):
        return "\\n".join(lines[1:]).strip()
    return context.strip()


def truncate_context(text, max_chars):
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]

    cut_idx = truncated.rfind("\\n\\n")
    if cut_idx >= max_chars // 3:
        return truncated[:cut_idx].rstrip()

    cut_idx = truncated.rfind("\\n")
    if cut_idx >= max_chars // 3:
        return truncated[:cut_idx].rstrip()

    cut_idx = truncated.rfind(" ")
    if cut_idx >= max_chars // 3:
        return truncated[:cut_idx].rstrip()

    return truncated.rstrip()


def get_session_state_file(session_id, cwd):
    temp_dir = Path(tempfile.gettempdir())
    if session_id and isinstance(session_id, str):
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
        if safe_id:
            return temp_dir / ("llm_wiki_session_" + safe_id + ".json")

    cwd_hash = hashlib.sha256(str(cwd.resolve()).encode("utf-8")).hexdigest()[:16]
    return temp_dir / ("llm_wiki_session_" + cwd_hash + ".json")


def get_db_mtime(cwd: Path) -> float:
    try:
        env_db = os.environ.get("LLM_WIKI_DB")
        if env_db and Path(env_db).is_file():
            return Path(env_db).stat().st_mtime
        db_file = cwd / ".llm-wiki" / "wiki.db"
        if db_file.is_file():
            return db_file.stat().st_mtime
        config_file = cwd / ".llm-wiki" / "config.toml"
        if config_file.is_file():
            return config_file.stat().st_mtime
    except Exception:
        pass
    return 0.0


def is_duplicate_context(session_id, cwd, context_hash, db_mtime):
    state_file = get_session_state_file(session_id, cwd)
    if not state_file.is_file():
        return False
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False

        if data.get("last_context_hash") != context_hash:
            return False

        # Invalidate if TTL expired
        updated_at = float(data.get("updated_at", 0))
        if time.time() - updated_at > SESSION_TTL:
            return False

        # Invalidate if DB modified since last cache
        cached_mtime = float(data.get("cached_db_mtime", 0))
        if db_mtime > 0 and cached_mtime > 0 and db_mtime > cached_mtime:
            return False

        # Track stats on duplicate hit
        data["dedup_hits"] = int(data.get("dedup_hits", 0)) + 1
        data["saved_chars"] = int(data.get("saved_chars", 0)) + int(data.get("context_len", 0))
        data["updated_at"] = time.time()
        state_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def save_context_hash(session_id, cwd, context_hash, db_mtime, context_len):
    state_file = get_session_state_file(session_id, cwd)
    try:
        existing_hits = 0
        existing_saved_chars = 0
        if state_file.is_file():
            try:
                old_data = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(old_data, dict):
                    existing_hits = int(old_data.get("dedup_hits", 0))
                    existing_saved_chars = int(old_data.get("saved_chars", 0))
            except Exception:
                pass

        data = {{
            "last_context_hash": context_hash,
            "updated_at": time.time(),
            "cached_db_mtime": db_mtime,
            "context_len": context_len,
            "session_id": str(session_id),
            "cwd": str(cwd),
            "dedup_hits": existing_hits,
            "saved_chars": existing_saved_chars,
        }}
        state_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


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
