---
title: Browsing the Wiki in Obsidian
tags:
  - runbook
  - obsidian
  - graph
---

# Browsing the Wiki in Obsidian

The wiki's `docs/` folder is plain Markdown with `[[wikilinks]]`, so it opens
directly as an [Obsidian](https://obsidian.md) vault — no export or conversion.
This runbook covers day-to-day use. For the underlying mechanism see
[[references/knowledge-graph]]; return to the [[index]] for the page list.

## 1. Open the vault

1. In Obsidian: **Open folder as vault**.
2. Point it at the wiki's docs root:
   - Project wiki: `/path/to/project/docs`
   - Global wiki: `~/.llm-wiki/docs`
3. Trust the folder when prompted (these are your own notes).

The `.llm-wiki/wiki.db` index lives outside `docs/`, so Obsidian never shows it.

## 2. Turn on wikilinks

Obsidian resolves `[[page]]` links by default. Confirm under
**Settings → Files & Links**:

- **Use `[[Wikilinks]]`**: on
- **New link format**: *Shortest path when possible* (matches how targets are
  written here, e.g. `[[manual]]`, `[[decisions/hook-event-name-invariant]]`)

## 3. See the graph

- **Graph view** (left ribbon, or `Ctrl/Cmd+G`) draws every document as a node
  and every `[[wikilink]]` as an edge. The [[index]] page is the hub that most
  pages link back to.
- **Local graph** (from a note's ⋮ menu) shows just that page's neighbours.
- **Backlinks** (right sidebar) lists every page that links **to** the current
  one — the same set `llm-wiki links <id>` prints under `← backlinks`.

If a page appears as an isolated dot, it has no `[[wikilinks]]` yet — add one
back to the [[index]] to connect it. For an audit pass, enable **Orphans** in
Graph View settings (with **Existing files only** and **Tags** on) so
unconnected notes and unresolved targets are visible at a glance.

## 3b. Project hubs in the global vault

When projects are materialized into the global vault with
`llm-wiki vault import` (see [[runbooks/migrate-to-global-wiki]]), each
project lives under a namespace such as `projects/evbp-etl/`:

- `projects/<slug>/index.md` is the **project hub**; a managed block inside it
  links every imported note of that project.
- Every managed note carries a managed `Related: [[projects/<slug>/index]]`
  backlink, so no managed note is an orphan.
- The global `index.md` carries a managed block linking every project hub.
- Project tags are YAML list tags (`project:<slug>`), so they appear as
  separate tag nodes in Graph View instead of one comma-separated scalar.

Cross-check the whole surface with:

```bash
llm-wiki vault audit --home ~/.llm-wiki --db ~/.llm-wiki/wiki.db
```

It compares physical Markdown against indexed documents and reports orphan
nodes, unresolved wikilink targets, and indexed paths outside the vault.

**Rollback**: restore the backed-up `docs/` tree and DB from
`~/.llm-wiki/backups/`; source repositories are never modified by the import,
so no repo-side rollback is needed.

## 4. Conventions when adding pages

Keep Obsidian and the wiki engine in sync by following these when you write a
new document under `docs/`:

1. **Frontmatter** with a `title` and **YAML list tags**:

   ```markdown
   ---
   title: Deployment Rollback
   tags:
     - runbook
     - deployment
   ---
   ```

2. **Link it into the graph** — add at least one `[[index]]` link from the new
   page, and a `[[your-new-page]]` link from `index.md`, so it is never an
   orphan node.

3. **Re-index** so the engine stores the new edges:

   ```bash
   llm-wiki reindex          # whole docs root, or:
   llm-wiki add docs/runbooks/deployment-rollback.md
   ```

The `llm-wiki-promote` skill applies exactly these conventions automatically
when it promotes knowledge into the wiki.

## 5. Cross-check the graph from the CLI

Obsidian's graph is visual; the engine's is queryable. They should match:

```bash
llm-wiki search "<text>"      # find a document id
llm-wiki links <id>           # → outgoing links and ← backlinks
```

If Obsidian shows an edge that `llm-wiki links` does not, the index is stale —
run `llm-wiki reindex`.
