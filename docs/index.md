---
title: LLM Wiki Index
tags:
  - index
  - llm-wiki
---

# LLM Wiki Index

Use this page as the entry point for durable project knowledge.

## Sections

- `decisions/`: approved architecture and product decisions
- `runbooks/`: repeatable operating procedures
- `references/`: stable source notes and external references

## Pages

- [[manual]] — full CLI manual: init, indexing, retrieval, agent integration.
- [[example]] — architecture guide: how approved knowledge is stored and indexed.
- [[runbooks/obsidian-usage]] — open this folder in Obsidian, use the graph
  view, and the conventions for adding new pages.
- [[references/knowledge-graph]] — how wikilinks, the link table, resolution,
  and backlinks work under the hood.
- [[decisions/single-global-wiki-tag-scope]] — one global wiki, scoped by
  `project:` tags instead of per-project databases.
- [[decisions/hook-event-name-invariant]] — the hook event-name invariant and
  why there is no looping `Stop` hook.

Open this folder as an Obsidian vault to browse the same graph visually — every
double-bracketed link above becomes an edge in the graph view, and the wiki
engine tracks the same edges through `llm-wiki links <id>`. See
[[runbooks/obsidian-usage]] to get started.
