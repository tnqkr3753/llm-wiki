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

Nothing here is forced: per-project databases still work. Migrate only when you
want one graph scoped by `project:` tags instead of many isolated indexes.

## The one switch: `LLM_WIKI_DB`

Database resolution order is `--db` > `LLM_WIKI_DB` (env) > project config >
global config. Setting the environment variable makes every command use the
global database even inside a project that still has its own config.

```bash
llm-wiki init                                 # create ~/.llm-wiki if needed
export LLM_WIKI_DB="$HOME/.llm-wiki/wiki.db"   # add to your shell profile
```

To undo the migration at any time, `unset LLM_WIKI_DB` — the old per-project
behaviour returns immediately.

## Path A — keep docs in each repo (recommended, non-destructive)

Do not move files. Index each repo's `docs/` into the one global database; the
store indexes many roots into a single DB and stores canonical paths, so there
are no duplicates or collisions.

Per project:

1. Tag its project-specific documents in frontmatter:

   ```markdown
   ---
   title: Deploy Rollback
   tags:
     - runbook
     - project:my-app
   ---
   ```

2. Index that repo's docs into the global DB (with `LLM_WIKI_DB` set, `--db`
   is optional):

   ```bash
   llm-wiki reindex -p /path/to/my-app/docs
   ```

Retrieve by scoping with tags instead of switching databases:

```bash
llm-wiki search "deploy" --tag project:my-app
llm-wiki ask-context "how do we deploy?" --tag project:my-app
llm-wiki search "deploy"          # no --tag spans the whole graph
```

Docs stay versioned in each repo, and cross-project `[[wikilinks]]` and
backlinks now actually connect.

## Path B — consolidate files into the global home

If you would rather keep all Markdown under `~/.llm-wiki/docs/`:

```bash
cp -r /path/to/my-app/docs/* ~/.llm-wiki/docs/   # add project: tags as you go
llm-wiki reindex -p ~/.llm-wiki/docs
```

Trade-off: you lose per-repo portability. Prefer Path A unless a repo has no
reason to keep its own docs.

## Checklist

1. **Tag rule** — project-specific docs get `project:<name>`; cross-project
   knowledge gets no `project:` tag.
2. **Reinstall skills** so agents resolve the global DB by default:

   ```bash
   llm-wiki claude install-skill -g --force    # or codex / gemini
   ```

3. **Old project DBs** — delete them after migrating, or keep them. A repo that
   needs hard isolation can keep using `--db /path/.llm-wiki/wiki.db`.
4. **Rollback** — `unset LLM_WIKI_DB` restores per-project behaviour.

## Safe to run repeatedly

`reindex` only prunes missing documents **within the root you pass**, so indexing
repo A into the global DB never deletes repo B's documents. Re-running any step
is idempotent.
