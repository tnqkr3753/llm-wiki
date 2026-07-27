---
title: LLM Wiki Manual
tags:
  - manual
  - llm-wiki
  - runbook
---

# LLM Wiki Manual

LLM Wiki is a local-first knowledge base for Codex and other LLM agents. It
stores approved Markdown knowledge, indexes it into SQLite FTS5, and returns
source-grounded context through the CLI.

Start from the [[index]] for the page list, or read the [[example]] architecture
guide. Hook design rules are in [[decisions/hook-event-name-invariant]].

## 1. Initialize The Global Wiki

Install the CLI once:

```bash
uv tool install git+https://github.com/tnqkr3753/llm-wiki.git
```

Then prepare the common wiki:

```bash
llm-wiki init
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
llm-wiki init --home /path/to/common/wiki
```

You can also set `LLM_WIKI_HOME=/path/to/common/wiki` so future commands use
that home by default.

## 2. Initialize A Project

Prepare another project:

```bash
llm-wiki project init -p /path/to/project
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
llm-wiki project init -p /path/to/project --agents
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
llm-wiki add docs/runbooks/deployment.md
```

## 4. Retrieve Context

Search as a human:

```bash
llm-wiki search deployment
```

Prepare context for Codex or another LLM:

```bash
llm-wiki ask-context "How do we deploy?"
```

The output is intentionally plain text so it can be pasted into an agent prompt.

### Scoping with tags

LLM Wiki is one connected knowledge graph, so the recommended setup is a single
global wiki with project-specific documents tagged `project:<name>` rather than
split into separate databases (see `docs/decisions/single-global-wiki-tag-scope.md`).
Use `--tag` to scope any search to documents carrying every given tag (exact
match, repeatable):

```bash
llm-wiki search deployment --tag project:my-app
llm-wiki ask-context "How do we deploy?" --tag project:my-app --tag runbook
```

With no `--tag`, retrieval spans the whole graph.

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

Install the LLM Wiki Codex skills once:

```bash
llm-wiki codex install-skill
```

By default this writes generated `SKILL.md` files under
`~/.agents/skills/llm-wiki-*`. Use `--skills-dir <path>` for a different Codex
skills directory, or `--force` to replace existing generated skills.

Generated skill language defaults to `--language auto`. Auto mode follows
`LC_ALL`, `LC_MESSAGES`, or `LANG` when they indicate Korean; otherwise it falls
back to English. Use `--language ko` or `--language en` to make the generated
skill language explicit:

```bash
llm-wiki codex install-skill --language ko
```

Installed Codex skills:

| Skill | Installed Markdown | Description |
|---|---|---|
| `llm-wiki-init` | `~/.agents/skills/llm-wiki-init/SKILL.md` | Use when setting up LLM Wiki globally or for a project. It initializes storage, docs folders, and project-local `AGENTS.md` instructions so Codex can query the right wiki DB. |
| `llm-wiki-recall` | `~/.agents/skills/llm-wiki-recall/SKILL.md` | Use before project-specific or shared-context work when the answer depends on previous decisions, project rules, runbooks, architecture, or implementation context. The skill reads project instructions/config, runs `llm-wiki ask-context`, and asks Codex to separate wiki-grounded facts from inference. |
| `llm-wiki-promote` | `~/.agents/skills/llm-wiki-promote/SKILL.md` | Use when stable knowledge should become durable Wiki content. It writes or updates Markdown under the right docs folder, indexes it with `llm-wiki add`, and verifies recall. |
| `llm-wiki-maintain` | `~/.agents/skills/llm-wiki-maintain/SKILL.md` | Use when auditing, repairing, reindexing, or checking freshness of an LLM Wiki project or global home. It inspects safely, reindexes Markdown, checks config/AGENTS.md wiring, and reports findings. |
| `llm-wiki-hooks` | `~/.agents/skills/llm-wiki-hooks/SKILL.md` | Use when installing or verifying project-local Codex hooks for LLM Wiki. It runs `llm-wiki codex install-hooks`, checks the generated `UserPromptSubmit` hook, and reminds the user to trust it in `/hooks`. |

Install project-local Codex hooks when a project should automatically retrieve
Wiki context before each prompt:

```bash
llm-wiki codex install-hooks -p /path/to/project
```

This writes:

```text
/path/to/project/.codex/hooks.json
/path/to/project/.codex/hooks/llm_wiki_user_prompt.py
```

The hook runs on `UserPromptSubmit`. It is read-only: it checks for project
`.llm-wiki/config.toml`, `LLM_WIKI_DB`, or `LLM_WIKI_HOME`, runs
`llm-wiki ask-context`, and returns `additionalContext` only when Wiki context
exists. Codex requires non-managed project hooks to be reviewed and trusted in
`/hooks` before they run.

Hook choice:

- Use `UserPromptSubmit` for Wiki recall because it runs right before the user
  prompt is sent and can add `additionalContext`.
- `SessionStart` is acceptable later for light startup guidance, such as
  telling Codex that the project has LLM Wiki configured. Avoid full search
  there because it has no user question yet.
- `PreToolUse` and `PostToolUse` are better for command or file guardrails, not
  normal Wiki retrieval.
- Avoid `Stop` and `PostCompact` for automatic promotion. Wiki promotion should
  stay explicit through `llm-wiki-promote`.

For each project that should use LLM Wiki, run:

```bash
uv run llm-wiki project init -p /path/to/project --agents
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

For global/common knowledge, use the same `llm-wiki-promote` skill. Write the
Markdown file under `~/.llm-wiki/docs/decisions/`,
`~/.llm-wiki/docs/runbooks/`, or `~/.llm-wiki/docs/references/`, then let the
CLI resolve the global DB:

```bash
uv run --directory /path/to/llm-wiki llm-wiki add ~/.llm-wiki/docs/references/example.md
uv run --directory /path/to/llm-wiki llm-wiki ask-context "example"
```

If the common wiki lives somewhere else, set `LLM_WIKI_HOME=/path/to/common/wiki`
and write under `$LLM_WIKI_HOME/docs/` instead.

## 7. Claude Code Integration

Install the same five LLM Wiki skills for Claude Code:

```bash
llm-wiki claude install-skill
```

By default this writes generated `SKILL.md` files under
`~/.claude/skills/llm-wiki-*`. The `--skills-dir`, `--tool-path`, `--language`,
and `--force` options behave exactly like the Codex installer.

Install project-local Claude Code hooks:

```bash
llm-wiki claude install-hooks -p /path/to/project
```

This writes:

```text
/path/to/project/.claude/settings.json
/path/to/project/.claude/hooks/llm_wiki_user_prompt.py
```

The hook is merged into the `hooks.UserPromptSubmit` section of
`.claude/settings.json`; other settings in that file are preserved. Like the
Codex hook, it is read-only and adds `additionalContext` only when Wiki context
exists. Claude Code requires hooks changed outside the app to be reviewed in
`/hooks` before they run.

## 8. Gemini CLI Integration

Install the same five LLM Wiki skills for Gemini CLI:

```bash
llm-wiki gemini install-skill
```

By default this writes generated `SKILL.md` files under
`~/.gemini/skills/llm-wiki-*`. Gemini CLI reads the same `SKILL.md` format, so
the options and generated content match the other installers.

Install project-local Gemini CLI hooks:

```bash
llm-wiki gemini install-hooks -p /path/to/project
```

This writes:

```text
/path/to/project/.gemini/settings.json
/path/to/project/.gemini/hooks/llm_wiki_user_prompt.py
```

Gemini CLI has no `UserPromptSubmit` event; the equivalent is `BeforeAgent`,
which runs right before the agent handles the submitted prompt. The hook is
merged into the `hooks.BeforeAgent` section of `.gemini/settings.json` with a
5000 ms timeout (Gemini hook timeouts are in milliseconds), and other settings
in that file are preserved. Restart Gemini CLI after installing so the settings
are reloaded, and trust the project folder when prompted.

## 9. Agent Memory Handoff

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
