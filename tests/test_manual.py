from pathlib import Path


def test_manual_mentions_init_codex_and_agent_memory() -> None:
    manual = Path("docs/manual.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    combined = manual + "\n" + readme

    assert "llm-wiki init" in combined
    assert "AGENTS.md" in combined
    assert "Codex" in combined
    assert "Agent Memory" in combined
    assert "ask-context" in combined
    assert "--db /path/to/project/.llm-wiki/wiki.db" in combined
    assert "llm-wiki init" in combined
    assert "llm-wiki project init -p" in combined
    assert "llm-wiki codex install-skill" in combined
    assert "llm-wiki codex install-hooks" in combined
    assert "llm-wiki claude install-skill" in combined
    assert "llm-wiki claude install-hooks" in combined
    assert "llm-wiki gemini install-skill" in combined
    assert "llm-wiki gemini install-hooks" in combined
    assert "~/.claude/skills" in combined
    assert "~/.gemini/skills" in combined
    assert ".claude/settings.json" in combined
    assert ".gemini/settings.json" in combined
    assert "BeforeAgent" in combined
    assert "UserPromptSubmit" in combined
    assert "SessionStart" in combined
    assert "PreToolUse" in combined
    assert "Stop" in combined
    assert "--language auto" in combined
    assert "--language ko" in combined
    assert "Installed Codex skills" in combined
    assert "llm-wiki-init" in combined
    assert "llm-wiki-recall" in combined
    assert "llm-wiki-promote" in combined
    assert "llm-wiki-maintain" in combined
    assert "llm-wiki-hooks" in combined
    assert "wiki-grounded facts from inference" in combined
    assert "global/common knowledge" in combined or "전역/공통 지식" in combined
    assert "~/.llm-wiki/docs/references" in combined
    assert "~/.llm-wiki" in combined
    assert "LLM_WIKI_HOME" in combined
    assert "LLM_WIKI_DB" in combined


def test_docs_describe_the_physical_global_vault() -> None:
    decision = Path("docs/decisions/single-global-wiki-tag-scope.md").read_text(
        encoding="utf-8"
    )
    migrate = Path("docs/runbooks/migrate-to-global-wiki.md").read_text(
        encoding="utf-8"
    )
    obsidian = Path("docs/runbooks/obsidian-usage.md").read_text(encoding="utf-8")
    graph = Path("docs/references/knowledge-graph.md").read_text(encoding="utf-8")
    index = Path("docs/index.md").read_text(encoding="utf-8")
    combined = f"{decision}\n{migrate}\n{obsidian}\n{graph}\n{index}"

    assert "llm-wiki vault import" in combined
    assert "llm-wiki vault audit" in combined
    assert "--source evbp-etl=/Users/yuntaepark/Work/evbp-etl/docs" in combined
    assert "--apply" in combined
    assert "project:evbp-etl" in combined
    assert (
        "Obsidian only sees files inside the opened vault" in combined
        or "Obsidian은 열린 vault 안의 파일만 본다" in combined
    )
    assert "docs/projects/evbp-etl/" in combined
    assert "--project" in combined
    assert "cp -r" not in migrate
