# LLM Wiki

Local-first wiki for LLM and agent knowledge. The MVP indexes Markdown files
with YAML-style frontmatter into SQLite FTS5 and exposes a CLI for retrieval.

## Setup

Install the CLI from GitHub:

```bash
uv tool install git+https://github.com/tnqkr3753/llm-wiki.git
```

Upgrade an existing install:

```bash
uv tool upgrade llm-wiki
```

For local development, install dependencies in the checkout:

```bash
uv sync
```

## Usage

Initialize the global wiki used for common knowledge:

```bash
llm-wiki init
```

By default this creates `~/.llm-wiki/wiki.db`, `~/.llm-wiki/config.toml`, and
`~/.llm-wiki/docs/`. Use `--home <path>` or `LLM_WIKI_HOME=<path>` when the
common repository should live somewhere else.

Initialize a project-local wiki layout:

```bash
llm-wiki project init -p /path/to/project
```

Initialize a project and write Codex `AGENTS.md` instructions:

```bash
llm-wiki project init -p /path/to/project --agents
```

Install the LLM Wiki Codex skills:

```bash
llm-wiki codex install-skill
```

By default `--language auto` uses the shell locale. Use `--language ko` or
`--language en` when the generated skills should be explicit.

Install project-local Codex hooks:

```bash
llm-wiki codex install-hooks -p /path/to/project
```

This writes `.codex/hooks.json` and a `UserPromptSubmit` hook script that
injects `llm-wiki ask-context` results when the project has LLM Wiki configured.
Review and trust the hook with Codex `/hooks` before it runs.

Installed Codex skills:

| Skill | Description |
|---|---|
| `llm-wiki-init` | Sets up global or project-local LLM Wiki storage, docs folders, and Codex `AGENTS.md` instructions. |
| `llm-wiki-recall` | Looks up durable project knowledge with `llm-wiki ask-context` before Codex answers or changes code, then separates wiki-grounded facts from inference. |
| `llm-wiki-promote` | Promotes stable decisions, runbooks, source notes, or Agent Memory findings into Markdown docs and indexes them with `llm-wiki add`. |
| `llm-wiki-maintain` | Audits, reindexes, and checks freshness of project or global wiki docs without deleting user content. |
| `llm-wiki-hooks` | Installs and verifies project-local Codex `UserPromptSubmit` hooks for automatic Wiki context injection. |

Index one Markdown document:

```bash
llm-wiki add docs/example.md
```

Search the local index:

```bash
llm-wiki search architecture
```

Show a stored document:

```bash
llm-wiki show 1
```

Print source-grounded context for an LLM prompt:

```bash
llm-wiki ask-context "approved knowledge"
```

Database path resolution is explicit and predictable:

```text
--db
LLM_WIKI_DB
nearest project .llm-wiki/config.toml
LLM_WIKI_HOME/config.toml or ~/.llm-wiki/config.toml
~/.llm-wiki/wiki.db
```

Project config discovery starts at the command's current working directory.
When Codex runs through `uv run --directory <tool-repo>`, keep using explicit
`--db` for the target project.

See [docs/manual.md](docs/manual.md) for the full manual, including Codex
integration and Agent Memory handoff.

During development, prefix commands with `uv run` from this repository:

```bash
uv run llm-wiki search architecture
```
