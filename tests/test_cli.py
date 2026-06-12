import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_wiki.cli import app

runner = CliRunner()


def write_doc(path: Path, title: str, body: str) -> None:
    _ = path.write_text(
        f"---\ntitle: {title}\ntags: architecture, runbook\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_add_then_search_indexes_markdown(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_path = docs_dir / "architecture.md"
    db_path = tmp_path / "wiki.db"
    write_doc(
        doc_path,
        "Architecture Guide",
        "The architecture uses SQLite FTS for grounded retrieval.",
    )

    add_result = runner.invoke(app, ["add", str(doc_path), "--db", str(db_path)])
    search_result = runner.invoke(app, ["search", "architecture", "--db", str(db_path)])

    assert add_result.exit_code == 0
    assert "indexed" in add_result.output
    assert search_result.exit_code == 0
    assert "Architecture Guide" in search_result.output
    assert str(doc_path) in search_result.output


def test_help_exposes_only_public_search_command() -> None:
    help_result = runner.invoke(app, ["--help"])

    assert help_result.exit_code == 0
    assert "project" in help_result.output
    assert "search-command" not in help_result.output
    assert "search" in help_result.output


def test_search_treats_punctuation_query_as_literal_terms(tmp_path: Path) -> None:
    doc_path = tmp_path / "query.md"
    db_path = tmp_path / "wiki.db"
    write_doc(
        doc_path,
        "Query Syntax",
        'Does search survive punctuation like what? and quotes "inside" text.',
    )

    add_result = runner.invoke(app, ["add", str(doc_path), "--db", str(db_path)])
    search_result = runner.invoke(app, ["search", "what?", "--db", str(db_path)])

    assert add_result.exit_code == 0
    assert search_result.exit_code == 0
    assert "Traceback" not in search_result.output
    assert "Query Syntax" in search_result.output


def test_env_db_path_is_used_when_db_option_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_path = tmp_path / "env.md"
    db_path = tmp_path / "env-wiki.db"
    monkeypatch.setenv("LLM_WIKI_DB", str(db_path))
    write_doc(doc_path, "Env Wiki", "Environment configuration selects the DB.")

    add_result = runner.invoke(app, ["add", str(doc_path)])
    search_result = runner.invoke(app, ["search", "Environment"])

    assert add_result.exit_code == 0
    assert db_path.is_file()
    assert search_result.exit_code == 0
    assert "Env Wiki" in search_result.output


def test_add_missing_file_fails_without_indexing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.md"
    db_path = tmp_path / "wiki.db"

    add_result = runner.invoke(app, ["add", str(missing_path), "--db", str(db_path)])
    search_result = runner.invoke(app, ["search", "missing", "--db", str(db_path)])

    assert add_result.exit_code != 0
    assert "does not exist" in add_result.output
    assert search_result.exit_code == 0
    assert "No results" in search_result.output


def test_show_returns_document(tmp_path: Path) -> None:
    doc_path = tmp_path / "runbook.md"
    db_path = tmp_path / "wiki.db"
    write_doc(doc_path, "Runbook", "Restart the indexer after schema changes.")

    add_result = runner.invoke(app, ["add", str(doc_path), "--db", str(db_path)])
    show_result = runner.invoke(app, ["show", "1", "--db", str(db_path)])

    assert add_result.exit_code == 0
    assert show_result.exit_code == 0
    assert "Runbook" in show_result.output
    assert "Restart the indexer" in show_result.output


def test_ask_context_returns_grounded_snippets(tmp_path: Path) -> None:
    doc_path = tmp_path / "agent-memory.md"
    db_path = tmp_path / "wiki.db"
    write_doc(
        doc_path,
        "Agent Memory Comparison",
        "Agent Memory captures notes. LLM Wiki stores approved knowledge.",
    )

    add_result = runner.invoke(app, ["add", str(doc_path), "--db", str(db_path)])
    context_result = runner.invoke(
        app,
        ["ask-context", "approved knowledge", "--db", str(db_path), "--limit", "1"],
    )

    assert add_result.exit_code == 0
    assert context_result.exit_code == 0
    assert "Use this context" in context_result.output
    assert "Agent Memory Comparison" in context_result.output
    assert "approved knowledge" in context_result.output


def test_project_init_creates_project_wiki_layout(tmp_path: Path) -> None:
    project_path = tmp_path / "project"

    init_result = runner.invoke(app, ["project", "init", "-p", str(project_path)])

    assert init_result.exit_code == 0
    assert "initialized" in init_result.output
    assert (project_path / ".llm-wiki" / "wiki.db").is_file()
    assert (project_path / ".llm-wiki" / "config.toml").is_file()
    assert (project_path / "docs" / "index.md").is_file()
    assert (project_path / "docs" / "decisions").is_dir()
    assert (project_path / "docs" / "runbooks").is_dir()
    assert (project_path / "docs" / "references").is_dir()


def test_project_config_db_path_is_used_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = tmp_path / "project"
    doc_path = project_path / "docs" / "references" / "configured.md"

    init_result = runner.invoke(app, ["project", "init", "-p", str(project_path)])
    _ = (project_path / ".llm-wiki" / "config.toml").write_text(
        'docs_dir = "docs"\ndb_path = "custom/wiki.db"\n',
        encoding="utf-8",
    )
    write_doc(doc_path, "Configured Wiki", "Project config selects the local DB.")
    monkeypatch.chdir(project_path)
    add_result = runner.invoke(app, ["add", str(doc_path)])
    search_result = runner.invoke(app, ["search", "configured"])

    assert init_result.exit_code == 0
    assert add_result.exit_code == 0
    assert (project_path / "custom" / "wiki.db").is_file()
    assert search_result.exit_code == 0
    assert "Configured Wiki" in search_result.output


def test_init_agents_writes_codex_instructions(tmp_path: Path) -> None:
    project_path = tmp_path / "project"

    init_result = runner.invoke(
        app,
        ["project", "init", "-p", str(project_path), "--agents"],
    )

    agents_text = (project_path / "AGENTS.md").read_text(encoding="utf-8")
    assert init_result.exit_code == 0
    assert "AGENTS.md" in init_result.output
    assert "llm-wiki ask-context" in agents_text
    assert "llm-wiki add" in agents_text
    assert f"--db {project_path / '.llm-wiki' / 'wiki.db'}" in agents_text
    assert "Agent Memory" in agents_text


def test_init_agents_appends_llm_wiki_section_to_existing_agents(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    agents_path = project_path / "AGENTS.md"
    _ = agents_path.write_text(
        "# Existing Instructions\n\nDo not remove this.\n",
        encoding="utf-8",
    )

    init_result = runner.invoke(
        app,
        ["project", "init", "-p", str(project_path), "--agents"],
    )

    agents_text = agents_path.read_text(encoding="utf-8")
    assert init_result.exit_code == 0
    assert "# Existing Instructions" in agents_text
    assert "Do not remove this." in agents_text
    assert "llm-wiki ask-context" in agents_text
    assert "llm-wiki add" in agents_text


def test_codex_install_skill_writes_all_llm_wiki_skills(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    tool_path = tmp_path / "tool"

    install_result = runner.invoke(
        app,
        [
            "codex",
            "install-skill",
            "--skills-dir",
            str(skills_dir),
            "--tool-path",
            str(tool_path),
        ],
    )

    expected_skills = {
        "llm-wiki-init": "project init",
        "llm-wiki-recall": "ask-context",
        "llm-wiki-promote": "llm-wiki add",
        "llm-wiki-maintain": "Reindex",
        "llm-wiki-hooks": "install-hooks",
    }
    assert install_result.exit_code == 0
    for skill_name, expected_text in expected_skills.items():
        skill_path = skills_dir / skill_name / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")
        assert f"installed Codex skill: {skill_path}" in install_result.output
        assert skill_path.is_file()
        assert f"name: {skill_name}" in skill_text
        assert expected_text in skill_text
        assert f"uv run --directory {tool_path}" in skill_text

    promote_text = (
        skills_dir / "llm-wiki-promote" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "~/.llm-wiki/docs/references/example.md" in promote_text
    assert "LLM_WIKI_HOME" in promote_text
    assert "global/common knowledge" in promote_text


def test_codex_install_skill_preserves_existing_skill_without_force(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "llm-wiki-promote"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    _ = skill_path.write_text("existing skill\n", encoding="utf-8")

    install_result = runner.invoke(
        app,
        ["codex", "install-skill", "--skills-dir", str(skills_dir)],
    )

    assert install_result.exit_code == 0
    assert "already exists" in install_result.output
    assert skill_path.read_text(encoding="utf-8") == "existing skill\n"
    assert (skills_dir / "llm-wiki-init" / "SKILL.md").is_file()
    assert (skills_dir / "llm-wiki-recall" / "SKILL.md").is_file()
    assert (skills_dir / "llm-wiki-maintain" / "SKILL.md").is_file()
    assert (skills_dir / "llm-wiki-hooks" / "SKILL.md").is_file()


def test_codex_install_skill_can_write_korean_skills(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"

    install_result = runner.invoke(
        app,
        ["codex", "install-skill", "--skills-dir", str(skills_dir), "--language", "ko"],
    )

    recall_text = (skills_dir / "llm-wiki-recall" / "SKILL.md").read_text(
        encoding="utf-8",
    )
    assert install_result.exit_code == 0
    assert "사용자의 언어" in recall_text
    assert "위키 근거" in recall_text


def test_codex_install_skill_auto_language_uses_locale(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"

    install_result = runner.invoke(
        app,
        ["codex", "install-skill", "--skills-dir", str(skills_dir)],
        env={"LANG": "ko_KR.UTF-8"},
    )

    recall_text = (skills_dir / "llm-wiki-recall" / "SKILL.md").read_text(
        encoding="utf-8",
    )
    assert install_result.exit_code == 0
    assert "사용자의 언어" in recall_text


def test_codex_install_hooks_writes_user_prompt_hook(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    tool_path = tmp_path / "tool"
    project_path.mkdir()

    install_result = runner.invoke(
        app,
        [
            "codex",
            "install-hooks",
            "-p",
            str(project_path),
            "--tool-path",
            str(tool_path),
        ],
    )

    hooks_path = project_path / ".codex" / "hooks.json"
    script_path = project_path / ".codex" / "hooks" / "llm_wiki_user_prompt.py"
    hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
    script_text = script_path.read_text(encoding="utf-8")
    hook_command = hooks_data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert install_result.exit_code == 0
    assert "installed Codex hooks" in install_result.output
    assert script_path.is_file()
    assert "llm-wiki ask-context" in script_text
    assert "hookSpecificOutput" in script_text
    assert str(script_path) in hook_command
    assert hooks_data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] == 5


def test_codex_install_hooks_preserves_existing_hooks_json(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    codex_path = project_path / ".codex"
    codex_path.mkdir(parents=True)
    hooks_path = codex_path / "hooks.json"
    _ = hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 existing.py",
                                },
                            ],
                        },
                    ],
                },
            },
        ),
        encoding="utf-8",
    )

    install_result = runner.invoke(
        app,
        ["codex", "install-hooks", "-p", str(project_path)],
    )

    hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert install_result.exit_code == 0
    assert "SessionStart" in hooks_data["hooks"]
    assert "UserPromptSubmit" in hooks_data["hooks"]
    assert hooks_data["hooks"]["SessionStart"][0]["hooks"][0]["command"] == (
        "python3 existing.py"
    )


def test_init_creates_home_wiki_layout(tmp_path: Path) -> None:
    home_path = tmp_path / "home-wiki"

    init_result = runner.invoke(
        app,
        ["init", "--home", str(home_path)],
    )

    assert init_result.exit_code == 0
    assert "initialized global" in init_result.output
    assert (home_path / "wiki.db").is_file()
    assert (home_path / "config.toml").is_file()
    assert (home_path / "docs" / "index.md").is_file()
    assert (home_path / "docs" / "decisions").is_dir()
    assert (home_path / "docs" / "runbooks").is_dir()
    assert (home_path / "docs" / "references").is_dir()


def test_invalid_project_config_fails_without_global_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = tmp_path / "project"
    home_path = tmp_path / "global"
    global_doc_path = home_path / "docs" / "references" / "global.md"
    project_doc_path = project_path / "docs" / "references" / "project.md"

    global_init = runner.invoke(app, ["init", "--home", str(home_path)])
    project_init = runner.invoke(app, ["project", "init", "-p", str(project_path)])
    write_doc(global_doc_path, "Global Wiki", "configured fallback target")
    write_doc(project_doc_path, "Project Wiki", "configured project target")
    global_add = runner.invoke(
        app,
        ["add", str(global_doc_path), "--db", str(home_path / "wiki.db")],
    )
    _ = (project_path / ".llm-wiki" / "config.toml").write_text(
        'docs_dir = "docs"\ndb_path = "broken\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(project_path)
    monkeypatch.setenv("LLM_WIKI_HOME", str(home_path))

    search_result = runner.invoke(app, ["search", "configured"])

    assert global_init.exit_code == 0
    assert project_init.exit_code == 0
    assert global_add.exit_code == 0
    assert search_result.exit_code != 0
    assert "Invalid LLM Wiki config" in search_result.output
    assert "Global Wiki" not in search_result.output
