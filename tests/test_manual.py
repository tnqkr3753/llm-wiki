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
    assert "Installed Codex skills" in combined
    assert "llm-wiki-init" in combined
    assert "llm-wiki-recall" in combined
    assert "llm-wiki-promote" in combined
    assert "llm-wiki-maintain" in combined
    assert "wiki-grounded facts from inference" in combined
    assert "~/.llm-wiki" in combined
    assert "LLM_WIKI_HOME" in combined
    assert "LLM_WIKI_DB" in combined
