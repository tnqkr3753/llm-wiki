---
title: One global wiki, scoped by project tags
tags:
  - decisions
  - llm-wiki
  - graph
---

# One global wiki, scoped by project tags

The default home for durable knowledge is the **single global wiki**
(`~/.llm-wiki`, or `$LLM_WIKI_HOME`). Project-specific knowledge is
distinguished by a `project:<name>` tag, **not** by a separate per-project
database.

Back to the [[index]]. The retrieval surface is in the [[manual]]; the graph
mechanism is in [[references/knowledge-graph]].

## Why

LLM Wiki is a knowledge graph, and a graph's value is in its edges. Splitting
knowledge into one database per project makes cross-project edges structurally
impossible — a decision in project A can never link to a matching pattern in
project B. It also fragments the Obsidian graph view into disconnected vaults.

Isolation — the original reason for per-project databases — does not actually
require separate databases. Tags plus a retrieval-time filter give the same
separation while keeping every document in one connected graph.

## Convention

- Write durable knowledge under the global docs root
  (`~/.llm-wiki/docs/{decisions,runbooks,references}/`).
- Tag project-specific documents with `project:<name>` (e.g. `project:llm-wiki`)
  in addition to a kind tag (`decision`, `runbook`, `reference`).
- Truly cross-project knowledge simply omits any `project:` tag.

## SQLite graph versus the physical Obsidian vault

These are two different surfaces, and only one of them is visible in Obsidian:

- **The SQLite index** (`~/.llm-wiki/wiki.db`) can index Markdown from many
  roots at once. The CLI graph (`llm-wiki links`, search, backlinks) connects
  across all of them.
- **The physical vault** is a folder. Obsidian only sees files inside the
  opened vault — external paths that SQLite knows about never appear in
  Graph View, no matter how well they are indexed.

So the physical graph surface is `~/.llm-wiki/docs`. To make a project's
documents visible in the one Obsidian graph, they are materialized into a
collision-safe namespace such as `docs/projects/evbp-etl/` (for example,
`decisions/a.md` from `evbp-etl` becomes
`~/.llm-wiki/docs/projects/evbp-etl/decisions/a.md`), with the frontmatter
tag `project:evbp-etl`. `llm-wiki vault import` performs that
materialization dry-run-first; `llm-wiki vault audit` verifies that the
physical vault, the index, and the link graph agree. See
[[runbooks/migrate-to-global-wiki]].

## Retrieving within a scope

`--project` selects one project's slice plus global/common documents:

```bash
llm-wiki search "deploy" --project foo
llm-wiki ask-context "how do we deploy?" --project foo --tag runbook
```

`--tag` still filters to documents carrying every given tag, exact match.
No scope option searches the whole graph, which is the point — one wiki, one
graph, scoped only when you ask.

## What this does not remove

Per-project databases still work through `--db` / project `.llm-wiki/config.toml`
for anyone who needs hard isolation (e.g. a client repo that must never share an
index). They are simply no longer the default path.

Existing per-project users can move to this model with the
[[runbooks/migrate-to-global-wiki]] runbook.
