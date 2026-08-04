---
title: Migrating per-project wikis to the global wiki
tags:
  - runbook
  - llm-wiki
  - migration
---

# Migrating per-project wikis to the global wiki

For users who set up a separate `.llm-wiki/wiki.db` per project and now want the
single connected graph described in
[[decisions/single-global-wiki-tag-scope]]. Back to the [[index]]; retrieval
flags are in the [[manual]].

Nothing here is forced: per-project databases still work through
`mode = "isolated"`. Migrate only when you want one graph scoped by `project:`
tags instead of many isolated indexes.

## Project configuration

New projects default to the global wiki: `llm-wiki project init` writes
`mode = "global"` and a `project_tag` (for example `project:evbp-etl`) into
`.llm-wiki/config.toml` and creates no local DB. Existing projects switch by
adding those keys; a legacy config with only `db_path` stays isolated until
you do. Database resolution order is `--db` > `LLM_WIKI_DB` (env) > project
config (isolated mode only) > global config.

## Index-only option — keep docs in each repo

Indexing each repo's `docs/` into the one global database
(`llm-wiki reindex -p /path/to/my-app/docs --db ~/.llm-wiki/wiki.db`) makes
the **CLI** graph connected. But Obsidian only sees files inside the opened
vault, so this option does not make those files visible in the global Graph
View. Use the vault materializer below when you want one physical vault.

## Materialize the physical vault — dry-run first, then apply

`llm-wiki vault import` copies approved Markdown roots into namespaced paths
under `~/.llm-wiki/docs/projects/<slug>/`, normalizes only the `tags`
frontmatter field (adding `project:<slug>`), inserts a managed backlink to the
project hub, and links every hub from the global index. Source files are never
modified, moved, or deleted.

Run in this order:

1. **Back up** the global docs and every DB you touch (`rsync` the docs,
   `sqlite3 ... ".backup ..."` the databases).
2. **Dry-run** with every approved source root:

   ```bash
   llm-wiki vault import \
     --source evbp-etl=/Users/yuntaepark/Work/evbp-etl/docs \
     --source evbp-etl-dbt=/Users/yuntaepark/Work/evbp-etl-dbt/docs \
     --home ~/.llm-wiki
   ```

   The plan lists create/update/unchanged/conflict/skipped counts. A target
   that already exists but is not owned by a previous import manifest is a
   **conflict**; the import refuses to overwrite it. Symlinks escaping a
   source root are skipped and named.
3. **Apply** only when the dry-run reports zero conflicts, by re-running the
   same command with `--apply`. A JSON manifest (sources, hashes, actions) is
   written under `~/.llm-wiki/migrations/` before and after the switch.
4. **Rebuild a fresh DB** from the physical vault instead of pruning the old
   multi-root DB:

   ```bash
   llm-wiki reindex -p ~/.llm-wiki/docs --db ~/.llm-wiki/wiki.next.db
   ```

   Validate it, then atomically move the old DB into the backup directory and
   rename `wiki.next.db` to `wiki.db`.
5. **Audit**:

   ```bash
   llm-wiki vault audit --home ~/.llm-wiki --db ~/.llm-wiki/wiki.db
   ```

   Physical Markdown count must equal the indexed count, with zero external
   index paths, zero managed orphans, and zero unresolved managed targets.

Re-running the dry-run after apply must report everything `unchanged` —
the materializer is idempotent.

## Retrieval after migration

```bash
llm-wiki search "deploy" --project evbp-etl
llm-wiki ask-context "how do we deploy?" --project evbp-etl
llm-wiki search "deploy"          # no --project spans the whole graph
```

`--project` returns the selected project plus global/common documents and
excludes other projects.

## Checklist

1. **Tag rule** — project-specific docs get `project:<name>`; cross-project
   knowledge gets no `project:` tag.
2. **Reinstall skills** so agents resolve the global DB by default:

   ```bash
   llm-wiki claude install-skill -g --force    # or codex / gemini
   ```

3. **Old project DBs** — keep them; they are the rollback path. A repo that
   needs hard isolation keeps `mode = "isolated"` with its local
   `--db /path/.llm-wiki/wiki.db`.
4. **Rollback** — restore the backed-up global docs and DB, `unset
   LLM_WIKI_DB` if you exported it, and the untouched local DBs continue to
   work.

## Safe to run repeatedly

`reindex` only prunes missing documents **within the root you pass**, and
`vault import` refuses unmanaged targets, so re-running any step is
idempotent and never deletes another project's knowledge.
