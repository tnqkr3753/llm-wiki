"""Agent hook installation and registration.

This module writes the standalone hook scripts (whose source lives in
:mod:`llm_wiki.hook_templates`) into a project's agent config directory and
merges the matching entries into the agent's hook configuration file.
"""

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from llm_wiki.agents import HOOK_SCRIPT_NAME, TOOL_REPO_PATH, AgentKind, AgentTarget
from llm_wiki.hook_templates import (
    guardrail_script,
    prompt_hook_script,
    startup_script,
    stop_script,
)

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
    tool_path: Path | None = None,
    force: bool = True,
    include_prompt_auto_inject: bool = False,
) -> HookInstallResult:
    """Install the complete, optimized LLM Wiki agent hook suite."""
    resolved_project_path = project_path.expanduser().resolve()
    resolved_tool_path = TOOL_REPO_PATH if tool_path is None else tool_path

    # Install the smart hooks
    startup_res = install_startup_hook(target, resolved_project_path, force=force)
    _ = install_stop_hook(target, resolved_project_path, force=force)
    _ = install_guardrail_hook(target, resolved_project_path, force=force)

    config_dir = resolved_project_path / target.hook_dir_name
    hooks_dir = config_dir / "hooks"
    hooks_path = config_dir / target.hook_config_name
    script_path = hooks_dir / HOOK_SCRIPT_NAME

    if include_prompt_auto_inject:
        if force or not script_path.exists():
            _ = script_path.write_text(
                prompt_hook_script(target, str(resolved_tool_path.resolve())),
                encoding="utf-8",
            )
            script_path.chmod(0o755)

        hooks_data = _load_hooks_json(hooks_path)
        _merge_hook(hooks_data, target, script_path)
        hooks_path.write_text(
            json.dumps(hooks_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return HookInstallResult(hooks_path=hooks_path, script_path=startup_res.script_path)


def install_startup_hook(
    target: AgentTarget,
    project_path: Path,
    force: bool = True,
) -> HookInstallResult:
    """Install a lightweight (~15 token) SessionStart awareness hook for LLM Wiki."""
    return _install_smart_hook(
        target,
        project_path,
        script_name="llm_wiki_startup.py",
        script_source=startup_script(target),
        event_name=target.startup_event,
        force=force,
    )


def install_stop_hook(
    target: AgentTarget,
    project_path: Path,
    force: bool = True,
) -> HookInstallResult:
    """Install a SessionEnd / Stop advisor hook to remind about LLM Wiki promotion."""
    return _install_smart_hook(
        target,
        project_path,
        script_name="llm_wiki_stop.py",
        script_source=stop_script(target),
        event_name=target.stop_event,
        force=force,
    )


def install_guardrail_hook(
    target: AgentTarget,
    project_path: Path,
    force: bool = True,
) -> HookInstallResult:
    """Install a selective PreToolUse guardrail hook for sensitive file modifications."""
    return _install_smart_hook(
        target,
        project_path,
        script_name="llm_wiki_guardrail.py",
        script_source=guardrail_script(target),
        event_name=target.guardrail_event,
        force=force,
    )


def _install_smart_hook(
    target: AgentTarget,
    project_path: Path,
    *,
    script_name: str,
    script_source: str,
    event_name: str,
    force: bool,
) -> HookInstallResult:
    """Write one standalone hook script and register it under ``event_name``."""
    resolved_project_path = project_path.expanduser().resolve()
    config_dir = resolved_project_path / target.hook_dir_name
    hooks_dir = config_dir / "hooks"
    hooks_path = config_dir / target.hook_config_name
    script_path = hooks_dir / script_name

    hooks_dir.mkdir(parents=True, exist_ok=True)
    if force or not script_path.exists():
        script_path.write_text(script_source, encoding="utf-8")
        script_path.chmod(0o755)

    hooks_data = _load_hooks_json(hooks_path)
    _merge_event_entry(hooks_data, event_name, script_path)
    hooks_path.write_text(
        json.dumps(hooks_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return HookInstallResult(hooks_path=hooks_path, script_path=script_path)


def _merge_event_entry(
    hooks_data: dict[str, JsonValue],
    event_name: str,
    script_path: Path,
) -> None:
    """Append a command hook for ``script_path`` under ``event_name`` if absent."""
    hooks_value = hooks_data.get("hooks")
    if not isinstance(hooks_value, dict):
        hooks_value = {}
        hooks_data["hooks"] = hooks_value

    event_value = hooks_value.get(event_name)
    if not isinstance(event_value, list):
        event_value = []
        hooks_value[event_name] = event_value

    command = f"python3 {shlex.quote(str(script_path))}"
    if _has_llm_wiki_hook(event_value, command):
        return
    event_value.append({"hooks": [{"type": "command", "command": command, "timeout": 3}]})


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

    wiki_scripts = ("llm_wiki_user_prompt.py", "llm_wiki_startup.py", "llm_wiki_stop.py", "llm_wiki_guardrail.py")

    for event_name, event_value in list(hooks_value.items()):
        if not isinstance(event_value, list):
            continue

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
                if not (isinstance(h, dict) and any(s in str(h.get("command", "")) for s in wiki_scripts))
            ]
            if filtered_hooks:
                group["hooks"] = filtered_hooks
                new_event_value.append(group)

        hooks_value[event_name] = new_event_value


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
