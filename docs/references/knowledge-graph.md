---
title: How the Knowledge Graph Works
tags:
  - reference
  - graph
  - architecture
  - obsidian
---

# How the Knowledge Graph Works

LLM Wiki is not only a full-text index — it also tracks how documents link to
one another, so the same Markdown files render as a connected graph in Obsidian
and can be queried through the CLI. This page explains the mechanism end to end.

Back to the [[index]]. Practical steps for humans are in the
[[runbooks/obsidian-usage]] runbook; the storage rationale is in
[[example]].

## The two layers

1. **Full-text search** — every document is indexed into SQLite FTS5 (trigram),
   answering `search` / `ask-context`. This is content, not structure.
2. **Link graph** — every `[[wikilink]]` in a document body is parsed and stored
   as a directed edge. This is structure, not content. Both layers live in the
   same `wiki.db`.

The graph layer is what makes backlinks, the Obsidian graph view, and
`llm-wiki links` possible.

## Wikilink syntax that is recognized

The parser (`markdown.parse_wikilinks`) extracts targets from the document body:

| Written in Markdown | Stored target |
|---|---|
| `[[manual]]` | `manual` |
| `[[decisions/hook-event-name-invariant]]` | `decisions/hook-event-name-invariant` |
| `[[manual\|the CLI manual]]` (alias) | `manual` |
| `[[manual#Setup]]` (heading anchor) | `manual` |

Rules:

- The **alias** after `|` and the **anchor** after `#` are dropped — a link
  names a document, exactly as Obsidian resolves it.
- Targets are **deduplicated** and kept in first-seen order.
- Empty targets (`[[]]`) are ignored.
- A target is the path under the docs root **without** the `.md` suffix.

## How targets resolve to documents

A stored target string is resolved to an actual indexed document
(`store._resolve_target`) by, in order:

1. **Exact / suffix path match** — the document's stored path, minus `.md`,
   equals the target or ends with `/<target>`. This is what makes
   `[[decisions/hook-event-name-invariant]]` land on the right nested file.
2. **Basename match** — the document's file stem equals the target's last
   segment, so a bare `[[manual]]` finds `docs/manual.md`.

An unresolved target (a link to a page that is not indexed) is simply omitted
from the results — it never errors, mirroring an Obsidian "unresolved link".

## What is stored

On every `add` / `reindex`, `upsert_document` rewrites the document's outgoing
edges in the `document_links` table:

```
document_links(source_id INTEGER, target TEXT, PRIMARY KEY(source_id, target))
```

- Links are **replaced**, not appended: re-indexing a document that dropped a
  link removes that edge, so the graph never drifts from the file.
- When a document is removed during reindex, its rows in `document_links`
  (as a source) are deleted too.
- Targets are stored as the raw wikilink text and resolved at **query** time,
  so adding the target document later automatically connects existing links.

## Querying the graph

`llm-wiki links <id>` reports both directions:

- **Outgoing** (`store.outgoing_links`) — resolve this document's stored targets
  to indexed documents, in first-seen order, skipping self-links and
  unresolved targets.
- **Backlinks** (`store.backlinks`) — scan every edge, resolve its target, and
  collect the sources whose target resolves to this document.

Because resolution is shared, the Obsidian graph view and `llm-wiki links`
always agree on which edges exist — with one asymmetry: the SQLite index can
hold documents from many roots, but
Obsidian only sees files inside the opened vault.
An externally indexed path is a real node for `llm-wiki links` and
search, yet it never appears in Graph View. Making a document visible in the
one global graph therefore means physically materializing it under
`~/.llm-wiki/docs` (see [[runbooks/migrate-to-global-wiki]]), and
`llm-wiki vault audit` reports any indexed path that lives outside the vault.

## Why paths are canonical

Every document path is stored in canonical (resolved, absolute) form. Without
this, the same file indexed as `./docs/x.md` and `/abs/docs/x.md` — or `/tmp`
vs `/private/tmp` — would create duplicate nodes and split a document's edges
across two rows. Canonical paths keep one file as exactly one graph node.
