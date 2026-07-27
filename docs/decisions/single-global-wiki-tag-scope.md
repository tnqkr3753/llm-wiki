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

## Retrieving within a scope

`--tag` filters any search to documents carrying every given tag, exact match:

```bash
llm-wiki search "deploy" --tag project:foo
llm-wiki ask-context "how do we deploy?" --tag project:foo --tag runbook
```

No `--tag` searches the whole graph, which is the point — one wiki, one graph,
scoped only when you ask.

## What this does not remove

Per-project databases still work through `--db` / project `.llm-wiki/config.toml`
for anyone who needs hard isolation (e.g. a client repo that must never share an
index). They are simply no longer the default path.
