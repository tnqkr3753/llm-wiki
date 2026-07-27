---
title: Rank documents by grounding use, and only ask-context records it
tags: llm-wiki, project, store, ranking, decisions
---

# Retrieval usage ranking

A wiki's most valuable asset is not its content but **which content actually
gets used**. BM25 alone cannot tell a decision record that has grounded twenty
answers from one that has never been retrieved since the day it was written.
`document_usage` records `retrieved_count` and `last_retrieved_at` per
document, and search can weight by it.

## Only `ask-context` records a retrieval

`search` and `show` are for humans browsing. `ask-context` is what an agent
injects into a prompt, so it is the only command that counts a retrieval.
Mixing browsing into the signal would reward documents that people click on
rather than documents that answer questions.

## Scoring

`adjusted = bm25 * (1 + usage_weight * ln(1 + retrieved_count))`

The logarithm keeps a frequently used document from dominating forever — going
from 0 to 1 retrieval matters far more than from 40 to 41. `usage_weight`
defaults to 0 in `store.search()` (unchanged BM25 order) and to 0.3 in
`ask-context`, overridable with `--usage-weight`.

Re-ranking happens in Python, not SQL, because `log()` requires SQLite built
with `SQLITE_ENABLE_MATH_FUNCTIONS` and that cannot be assumed. To make the
re-rank meaningful, the query fetches more candidates than the final limit
(`max(limit * 4, 20)`) and truncates after sorting.

## Never-retrieved documents are a maintenance signal

`llm-wiki usage` separates retrieved documents from those with a count of
zero. A zero is not proof a document is worthless, but it does mean the wiki
never answered a question with it — either its wording does not match how
questions are asked, or it should not have been promoted. The
`llm-wiki-maintain` skill reports them; it never deletes them.

Usage rows are deleted along with their document when `reindex` prunes a
deleted file, so a path that is re-added later starts from zero rather than
inheriting a stale count.
