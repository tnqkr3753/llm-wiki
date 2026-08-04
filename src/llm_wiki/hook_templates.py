"""Source templates for the standalone hook scripts LLM Wiki installs.

These functions return the *source code* of the Python hook scripts that get
written into a project's ``.claude``/``.codex``/``.gemini`` hooks directory.
The scripts run as standalone ``python3`` processes without importing
``llm_wiki``, so their logic must be self-contained here. Installation and hook
registration logic lives in :mod:`llm_wiki.agent_hooks`.
"""

import json

from llm_wiki.agents import AgentTarget

__all__ = [
    "context_output_source",
    "guardrail_script",
    "prompt_hook_script",
    "startup_script",
]


def context_output_source(target: AgentTarget, event_name: str) -> str:
    """Return the JSON payload expression for a model-context-injecting hook.

    ``hookEventName`` must match the event the hook is registered under, and is
    validated by the agent CLI. Targets that carry the event name in their
    output (Claude/Codex) get it embedded; targets that do not (Gemini) emit a
    bare ``additionalContext`` payload.
    """
    if target.hook_output_includes_event:
        return (
            '{"hookEventName": '
            + json.dumps(event_name)
            + ', "additionalContext": context_text}'
        )
    return '{"additionalContext": context_text}'


def startup_script(target: AgentTarget) -> str:
    """SessionStart awareness hook: announces the project wiki is active."""
    hook_output_source = context_output_source(target, target.startup_event)
    return f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

def main():
    cwd = Path(os.getcwd())
    wiki_db = cwd / ".llm-wiki" / "wiki.db"
    if not wiki_db.is_file() and not os.environ.get("LLM_WIKI_DB"):
        return

    context_text = "[LLM Wiki] Project wiki active (.llm-wiki/wiki.db). Use skill 'llm-wiki-recall' for project rules or runbooks."
    print(json.dumps(
        {{"hookSpecificOutput": {hook_output_source}}},
        ensure_ascii=False,
    ))

if __name__ == "__main__":
    main()
"""


def guardrail_script(target: AgentTarget) -> str:
    """PreToolUse guardrail hook: warns when a sensitive file is being edited."""
    hook_output_source = context_output_source(target, target.guardrail_event)
    return f"""#!/usr/bin/env python3
import json
import sys

def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return

    tool_input = event.get("input") or event.get("tool_input") or {{}}
    file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")

    sensitive = ("schema.sql", "AGENTS.md", "config.toml", "settings.json", "Dockerfile", ".env")
    if any(s in file_path for s in sensitive):
        context_text = "[LLM Wiki Guardrail] Modifying sensitive file: " + file_path + ". Verify rules in LLM Wiki before committing changes."
        print(json.dumps(
            {{"hookSpecificOutput": {hook_output_source}}},
            ensure_ascii=False,
        ))

if __name__ == "__main__":
    main()
"""


def prompt_hook_script(
    target: AgentTarget,
    tool_path: str,
    db_path: str | None = None,
    project_slug: str | None = None,
) -> str:
    """UserPromptSubmit hook: retrieves and injects LLM Wiki context per prompt.

    ``db_path`` and ``project_slug`` are resolved at install time and embedded
    as constants, so the generated script does not depend on shell startup
    files (GUI-launched agents may never source them) nor parse TOML itself.
    """
    hook_output_source = context_output_source(target, target.hook_event)
    return f"""#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOL_PATH = {tool_path!r}
DB_PATH = {db_path!r}
PROJECT_SLUG = {project_slug!r}
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
        if DB_PATH and Path(DB_PATH).is_file():
            return Path(DB_PATH).stat().st_mtime
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
    if DB_PATH:
        return True
    if os.environ.get("LLM_WIKI_DB") or os.environ.get("LLM_WIKI_HOME"):
        return True
    for path in (cwd, *cwd.parents):
        if (path / ".llm-wiki" / "config.toml").is_file():
            return True
    return False


def ask_context(prompt, cwd):
    command = ["llm-wiki", "ask-context", prompt]
    if DB_PATH:
        command += ["--db", DB_PATH]
    if PROJECT_SLUG:
        command += ["--project", PROJECT_SLUG]
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
