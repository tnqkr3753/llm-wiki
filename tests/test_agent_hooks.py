"""Tests for agent hook installation and execution behavior."""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from llm_wiki.agent_hooks import install_agent_hooks
from llm_wiki.agents import ALL_TARGETS, CLAUDE_TARGET, CODEX_TARGET, AgentTarget


def test_hook_script_truncates_at_paragraph_boundary(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".llm-wiki").mkdir()
    (project_dir / ".llm-wiki" / "config.toml").write_text("", encoding="utf-8")

    result = install_agent_hooks(
        CODEX_TARGET, project_dir, tool_path=tmp_path / "tool", force=True, include_prompt_auto_inject=True
    )
    script_path = project_dir / ".codex" / "hooks" / "llm_wiki_user_prompt.py"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    p1 = "A" * 1200
    p2 = "B" * 1500
    fake_output = f"Use this context before answering:\n- [1] Test (test.md)\n  {p1}\n\n  {p2}"

    mock_cli = bin_dir / "llm-wiki"
    mock_cli.write_text(
        f"#!/usr/bin/env python3\nprint({fake_output!r})\n",
        encoding="utf-8",
    )
    mock_cli.chmod(0o755)

    import os
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}

    event = {
        "prompt": "explain EVBP",
        "cwd": str(project_dir),
        "session_id": f"test_session_trunc_{uuid.uuid4().hex}",
    }

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env,
    )

    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    context = data["hookSpecificOutput"]["additionalContext"]
    assert len(context) <= 2150
    assert "BBBB" not in context
    assert "AAAA" in context


def test_hook_script_deduplication(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".llm-wiki").mkdir()
    (project_dir / ".llm-wiki" / "config.toml").write_text("", encoding="utf-8")

    result = install_agent_hooks(
        CODEX_TARGET, project_dir, tool_path=tmp_path / "tool", force=True, include_prompt_auto_inject=True
    )
    script_path = project_dir / ".codex" / "hooks" / "llm_wiki_user_prompt.py"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    output_file = tmp_path / "output.txt"
    output_file.write_text(
        "Use this context before answering:\n" + ("X" * 150),
        encoding="utf-8",
    )

    mock_cli = bin_dir / "llm-wiki"
    mock_cli.write_text(
        f"#!/usr/bin/env python3\nfrom pathlib import Path\nprint(Path({str(output_file)!r}).read_text())\n",
        encoding="utf-8",
    )
    mock_cli.chmod(0o755)

    import os
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    session_id = f"test_session_dedup_{uuid.uuid4().hex}"
    event = {
        "prompt": "what is this",
        "cwd": str(project_dir),
        "session_id": session_id,
    }

    # First run: should output additionalContext
    proc1 = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc1.returncode == 0
    assert "hookSpecificOutput" in proc1.stdout

    # Second run with same context output: should be deduplicated (empty stdout)
    proc2 = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc2.returncode == 0
    assert proc2.stdout.strip() == ""

    # Third run with new context: should output additionalContext
    output_file.write_text(
        "Use this context before answering:\n" + ("Y" * 150),
        encoding="utf-8",
    )
    proc3 = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc3.returncode == 0
    assert "hookSpecificOutput" in proc3.stdout


def test_hook_script_filters_short_prompts_and_low_relevance_context(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".llm-wiki").mkdir()
    (project_dir / ".llm-wiki" / "config.toml").write_text("", encoding="utf-8")

    result = install_agent_hooks(
        CODEX_TARGET, project_dir, tool_path=tmp_path / "tool", force=True, include_prompt_auto_inject=True
    )
    script_path = project_dir / ".codex" / "hooks" / "llm_wiki_user_prompt.py"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mock_cli = bin_dir / "llm-wiki"
    mock_cli.write_text(
        "#!/usr/bin/env python3\nprint('Use this context before answering:\\n- [1] title')\n",
        encoding="utf-8",
    )
    mock_cli.chmod(0o755)

    import os
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}

    # Short prompt (< 3 chars)
    short_prompt_event = {
        "prompt": "ok",
        "cwd": str(project_dir),
        "session_id": f"test_short_{uuid.uuid4().hex}",
    }
    proc_short = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(short_prompt_event),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc_short.returncode == 0
    assert proc_short.stdout.strip() == ""

    # Low relevance context (< 100 chars clean body)
    normal_prompt_event = {
        "prompt": "tell me more details",
        "cwd": str(project_dir),
        "session_id": f"test_low_rel_{uuid.uuid4().hex}",
    }
    proc_low_rel = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(normal_prompt_event),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc_low_rel.returncode == 0
    assert proc_low_rel.stdout.strip() == ""


def _make_project(tmp_path: Path, *, with_db: bool = False) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    wiki_dir = project_dir / ".llm-wiki"
    wiki_dir.mkdir()
    (wiki_dir / "config.toml").write_text("", encoding="utf-8")
    if with_db:
        (wiki_dir / "wiki.db").write_text("", encoding="utf-8")
    return project_dir


def _run_script(script_path: Path, *, stdin: str = "", cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_startup_hook_emits_session_start_event(tmp_path: Path) -> None:
    project_dir = _make_project(tmp_path, with_db=True)
    install_agent_hooks(CLAUDE_TARGET, project_dir, force=True)
    script_path = project_dir / ".claude" / "hooks" / "llm_wiki_startup.py"

    data = _run_script(script_path, cwd=project_dir)
    output = data["hookSpecificOutput"]

    assert output["hookEventName"] == "SessionStart"
    assert output["hookEventName"] != "UserPromptSubmit"

    settings = json.loads(
        (project_dir / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "SessionStart" in settings["hooks"]


def test_guardrail_hook_emits_pre_tool_use_event(tmp_path: Path) -> None:
    project_dir = _make_project(tmp_path)
    install_agent_hooks(CLAUDE_TARGET, project_dir, force=True)
    script_path = project_dir / ".claude" / "hooks" / "llm_wiki_guardrail.py"

    event = {"tool_input": {"file_path": "/repo/.env"}}
    data = _run_script(script_path, stdin=json.dumps(event))
    output = data["hookSpecificOutput"]

    assert output["hookEventName"] == "PreToolUse"
    assert output["hookEventName"] != "UserPromptSubmit"
    assert ".env" in output["additionalContext"]

    settings = json.loads(
        (project_dir / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "PreToolUse" in settings["hooks"]


@pytest.mark.parametrize("target", ALL_TARGETS, ids=lambda t: t.kind.value)
def test_smart_hook_output_event_matches_registered_event(
    tmp_path: Path, target: AgentTarget
) -> None:
    # Invariant: for every target that embeds hookEventName, each smart hook's
    # emitted event name must equal the event key it is registered under.
    if not target.hook_output_includes_event:
        pytest.skip("target does not embed hookEventName in output")

    project_dir = tmp_path / target.kind.value
    project_dir.mkdir()
    wiki_dir = project_dir / ".llm-wiki"
    wiki_dir.mkdir()
    (wiki_dir / "config.toml").write_text("", encoding="utf-8")
    (wiki_dir / "wiki.db").write_text("", encoding="utf-8")

    install_agent_hooks(target, project_dir, force=True)
    hooks_dir = project_dir / target.hook_dir_name / "hooks"
    settings = json.loads(
        (project_dir / target.hook_dir_name / target.hook_config_name).read_text(
            encoding="utf-8"
        )
    )

    cases = [
        ("llm_wiki_startup.py", target.startup_event, "", project_dir),
        (
            "llm_wiki_guardrail.py",
            target.guardrail_event,
            json.dumps({"tool_input": {"file_path": "/repo/.env"}}),
            None,
        ),
    ]
    for script_name, event_name, stdin, cwd in cases:
        data = _run_script(hooks_dir / script_name, stdin=stdin, cwd=cwd)
        assert data["hookSpecificOutput"]["hookEventName"] == event_name
        assert event_name in settings["hooks"]
