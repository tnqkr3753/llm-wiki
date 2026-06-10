# LLM Wiki

Local-first wiki for LLM and agent knowledge. The MVP indexes Markdown files
with YAML-style frontmatter into SQLite FTS5 and exposes a CLI for retrieval.

## Setup

```bash
uv sync
```

## Usage

Initialize the global wiki used for common knowledge:

```bash
uv run llm-wiki init --global
```

By default this creates `~/.llm-wiki/wiki.db`, `~/.llm-wiki/config.toml`, and
`~/.llm-wiki/docs/`. Use `--home <path>` or `LLM_WIKI_HOME=<path>` when the
common repository should live somewhere else.

Initialize a project-local wiki layout:

```bash
uv run llm-wiki init --project /path/to/project
```

Initialize a project and write Codex `AGENTS.md` instructions:

```bash
uv run llm-wiki init --project /path/to/project --agents
```

Index one Markdown document:

```bash
uv run llm-wiki add docs/example.md
```

Search the local index:

```bash
uv run llm-wiki search architecture
```

Show a stored document:

```bash
uv run llm-wiki show 1
```

Print source-grounded context for an LLM prompt:

```bash
uv run llm-wiki ask-context "approved knowledge"
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
