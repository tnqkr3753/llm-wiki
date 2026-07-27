---
title: Reindex owns deletions, but only within the reindexed root
tags: llm-wiki, project, store, decisions
---

# Reindex deletion scope

`llm-wiki reindex` is the single command that makes the index match the
filesystem. It re-parses every Markdown file under a root **and removes index
entries whose source file is gone**. Before this, `reindex_directory()` only
upserted, so deleted or renamed documents lingered forever and `ask-context`
could ground an answer in a file that no longer exists.

## Deletion rule

A stored document is deleted from the index only when all of these hold:

1. its stored path is **absolute**,
2. it is **under the root** being reindexed, and
3. the file **does not exist** on disk.

Rules 1 and 2 exist because one database can index several roots — the global
home (`~/.llm-wiki/docs`) and any number of projects. Reindexing a project must
never evict another root's documents. A relative stored path (from an early
`llm-wiki add docs/foo.md` run) is never treated as stale: it was indexed
against an unknown working directory, so its absence cannot be proven.
`reindex_directory()` always writes absolute paths, so re-running it converges
the index onto absolute paths.

## Failures are reported, never swallowed

Parsing failures used to be discarded by a bare `except Exception: pass`.
`ReindexResult` now carries `indexed`, `removed`, and a `failures` tuple, the
CLI prints every failed path, and it exits non-zero. `parse_markdown_file()`
raises `DocumentReadError` on invalid UTF-8 as well as on OS errors, so a
corrupt file is surfaced instead of silently missing from the index.

## Hook contract

The Git `post-commit` hook installed by `llm-wiki git-hook install` calls
`llm-wiki reindex`, and it redirects all output to `/dev/null`. **Any command
referenced by a generated hook must exist in the CLI** — a typo or a renamed
command fails silently on every commit. `test_reindex.py` enforces this by
parsing the generated hook script and asserting every `llm-wiki <command>` it
invokes is registered on the Typer app.
