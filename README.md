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
`SessionStart` can be added later for light startup guidance, but `PreToolUse`,
`PostToolUse`, and `Stop` are not good defaults for Wiki recall.

The same integrations are available for Claude Code and Gemini CLI:

```bash
llm-wiki claude install-skill                       # ~/.claude/skills/llm-wiki-*
llm-wiki claude install-hooks -p /path/to/project   # .claude/settings.json (UserPromptSubmit)
llm-wiki gemini install-skill                       # ~/.gemini/skills/llm-wiki-*
llm-wiki gemini install-hooks -p /path/to/project   # .gemini/settings.json (BeforeAgent)
```

Claude Code uses the same `UserPromptSubmit` event and reviews externally added
hooks in `/hooks`. Gemini CLI uses its `BeforeAgent` event instead, and the
hook entry uses a millisecond timeout as Gemini expects.

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

Reindex every Markdown document under a project, including deletions:

```bash
llm-wiki reindex -p /path/to/project
```

`reindex` walks the project (skipping hidden and vendored directories),
re-indexes every Markdown file, and drops index entries whose source file no
longer exists. Only documents stored with an absolute path under that root are
removed, so reindexing one project never evicts another root's documents. The
command exits non-zero and names each file it could not parse.

Keep the index current automatically:

```bash
llm-wiki watch -p /path/to/project        # poll for changes and reindex
llm-wiki git-hook install -p /path/to/project  # reindex after each commit
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

`ask-context` is the only command that records retrievals, because grounding an
answer is the signal worth ranking on. Documents that have been retrieved
before are promoted over equally relevant ones that never were; pass
`--usage-weight 0` for pure BM25 order, or raise it to lean harder on history.

Report which documents are earning their place:

```bash
llm-wiki usage
```

Documents with a count of zero were never used to ground an answer — they are
promotion candidates that did not pay off, and the first thing to review when
the wiki grows noisy.

## Embedding (configuration only)

Retrieval is BM25 over a trigram FTS5 index. There is **no embedding backend
yet**, but the configuration surface is settled, so a local model can be wired
in later without changing these keys:

| Setting | Environment | Config `[embedding]` |
|---|---|---|
| model (required) | `LLM_WIKI_EMBED_MODEL` | `model` |
| endpoint | `LLM_WIKI_EMBED_URL` | `endpoint` |
| dimension | `LLM_WIKI_EMBED_DIM` | `dimension` |
| allow remote | `LLM_WIKI_EMBED_ALLOW_REMOTE` | `allow_remote` |

Fields resolve independently: environment first, then the nearest project
config, then the global config. Setting them changes nothing about search
today — only what `llm-wiki doctor` reports:

```bash
llm-wiki doctor
# - Embedding: Not configured (BM25 only)
# ✓ Embedding: bge-m3 via http://127.0.0.1:11434, dim 1024 - no backend installed yet
```

**Endpoints outside this machine are refused by default.** A wiki holds
internal decisions and runbooks, so a non-loopback host requires
`LLM_WIKI_EMBED_ALLOW_REMOTE=1`; otherwise `doctor` reports it as blocked.

See [docs/decisions/embedding-config-surface.md](docs/decisions/embedding-config-surface.md)
for the sizing measurements and why chunking has to come first.

## Database path resolution

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
