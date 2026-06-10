# LLM Wiki Manual

LLM Wiki is a local-first knowledge base for Codex and other LLM agents. It
stores approved Markdown knowledge, indexes it into SQLite FTS5, and returns
source-grounded context through the CLI.

## 1. Initialize The Global Wiki

Run this inside the LLM Wiki repository to prepare the common wiki:

```bash
uv run llm-wiki init --global
```

This creates:

```text
~/.llm-wiki/wiki.db
~/.llm-wiki/config.toml
~/.llm-wiki/docs/index.md
~/.llm-wiki/docs/decisions/
~/.llm-wiki/docs/runbooks/
~/.llm-wiki/docs/references/
```

Use a custom common repository when needed:

```bash
uv run llm-wiki init --global --home /path/to/common/wiki
```

You can also set `LLM_WIKI_HOME=/path/to/common/wiki` so future commands use
that home by default.

## 2. Initialize A Project

Run this inside the LLM Wiki repository to prepare another project:

```bash
uv run llm-wiki init --project /path/to/project
```

This creates:

```text
.llm-wiki/wiki.db
.llm-wiki/config.toml
docs/index.md
docs/decisions/
docs/runbooks/
docs/references/
```

Use `--agents` when the target project should teach Codex how to query the wiki:

```bash
uv run llm-wiki init --project /path/to/project --agents
```

That writes an `AGENTS.md` snippet with the `ask-context` and `add` commands.

## 3. Add Durable Knowledge

Create a Markdown document under `docs/` with frontmatter:

```markdown
---
title: Deployment Runbook
tags: runbook, deployment
---

Restart the worker after changing queue settings.
```

Index it:

```bash
uv run llm-wiki add docs/runbooks/deployment.md
```

## 4. Retrieve Context

Search as a human:

```bash
uv run llm-wiki search deployment
```

Prepare context for Codex or another LLM:

```bash
uv run llm-wiki ask-context "How do we deploy?"
```

The output is intentionally plain text so it can be pasted into an agent prompt.

## 5. Path Resolution

Every command that reads or writes the index resolves the SQLite database in
this order:

```text
1. --db /path/to/wiki.db
2. LLM_WIKI_DB=/path/to/wiki.db
3. nearest project .llm-wiki/config.toml db_path
4. LLM_WIKI_HOME/config.toml db_path, or ~/.llm-wiki/config.toml db_path
5. ~/.llm-wiki/wiki.db
```

Use `--db` for one-off commands, `LLM_WIKI_DB` for a temporary shell session,
project `.llm-wiki/config.toml` for a project wiki, and `LLM_WIKI_HOME` for the
shared common repository.

Project config discovery starts at the command's current working directory. If
Codex is running the CLI through `uv run --directory /path/to/llm-wiki`, keep
the explicit project `--db` argument in generated `AGENTS.md`.

## 6. Codex Integration

For each project that should use LLM Wiki, run:

```bash
uv run llm-wiki init --project /path/to/project --agents
```

The generated `AGENTS.md` tells Codex to call:

```bash
uv run --directory /path/to/llm-wiki llm-wiki ask-context "<question>" --db /path/to/project/.llm-wiki/wiki.db
```

When Codex promotes a reviewed document into the same project wiki, it should
also pass the project-local database explicitly:

```bash
uv run --directory /path/to/llm-wiki llm-wiki add /path/to/project/docs/<file>.md --db /path/to/project/.llm-wiki/wiki.db
```

before answering project-specific questions or making changes that depend on
existing decisions.

## 7. Agent Memory Handoff

Agent Memory is useful for temporary working observations and session recall.
LLM Wiki is for durable, reviewed knowledge. When an observation becomes a
stable rule, runbook, decision, or reference, promote it by writing a Markdown
document under `docs/` and indexing it with `llm-wiki add`.

Recommended flow:

```text
Agent Memory observation
-> human or agent reviews it
-> Markdown document under docs/
-> llm-wiki add
-> future Codex sessions retrieve it with ask-context
```
