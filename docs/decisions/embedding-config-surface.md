---
title: Embedding config surface ships before any backend, and remote endpoints are opt-in
tags: llm-wiki, project, embedding, retrieval, decisions
---

# Embedding configuration surface

Retrieval is SQLite FTS5 (BM25 over a trigram index) and stays that way for
now. What ships ahead of a backend is only the **configuration surface** and
the **provider contract**, so semantic search can be added later without
changing config keys, CLI flags, or user documentation a second time.

`load_provider()` returns `None` because no backend is installed, and every
search path is untouched. Setting the environment variables changes exactly
one thing today: what `llm-wiki doctor` reports.

## Resolution order

Each field resolves independently, environment first, then the nearest project
config, then the global config:

| Field | Environment | Config (`[embedding]`) |
|---|---|---|
| model | `LLM_WIKI_EMBED_MODEL` | `model` |
| endpoint | `LLM_WIKI_EMBED_URL` | `endpoint` |
| dimension | `LLM_WIKI_EMBED_DIM` | `dimension` |
| allow remote | `LLM_WIKI_EMBED_ALLOW_REMOTE` | `allow_remote` |

`model` is the required key: with no model configured anywhere, embedding is
simply off. Per-field resolution means an endpoint committed to project config
can be combined with a model name exported per machine.

## Remote endpoints are blocked by default

A wiki holds internal decisions, runbooks, and source notes. Auto-detecting an
ambient `OPENAI_API_KEY` or a remote `OLLAMA_HOST` and shipping document text
to it is not a default worth having — the failure mode is silent and
unrecoverable. Any endpoint whose host is not loopback is refused unless
`LLM_WIKI_EMBED_ALLOW_REMOTE=1` (or `allow_remote = true`) says otherwise, and
`doctor` reports the block rather than failing quietly.

## Any backend must stay optional

Runtime dependencies are typer and rich, so `uv tool install` finishes in
seconds. Pulling in torch or sentence-transformers as a hard dependency would
make that a multi-gigabyte install for a feature most projects will not turn
on. A backend belongs behind an extra (`llm-wiki[embed]`), and its absence must
fall back to BM25 rather than raise.

## Size is not the reason to hesitate

Measured on this repository's own wiki (7 documents, 20.9 KB of Markdown):

| Storage | Size | vs. raw text |
|---|---|---|
| trigram FTS index (in use today) | 136 KB | 6.5x |
| unicode61 FTS index | 72 KB | 3.4x |
| 35 chunks x 384-dim float32 | 80 KB | 3.8x |
| 35 chunks x 384-dim int8 | 36 KB | 1.7x |

The trigram tokenizer already costs more than embeddings would. Scaled to
1000 documents (~4 MB of Markdown): trigram ~26 MB, 5000 chunks at 384-dim
float32 ~7 MB, int8 ~2 MB. The database only bloats with 1536-dim vectors
stored as float32 (~29 MB), which is a model-choice problem, not an inherent
one.

The real cost is **recomputation**, not storage: `reindex` runs on every commit
via the post-commit hook, so a backend must hash chunk text and re-embed only
what changed.

## Chunking comes first

Embedding whole documents would waste the effort — one vector for `manual.md`
is vaguely similar to everything. Heading-level chunking is the prerequisite,
and it pays off on its own under BM25 by replacing the current
`snippet(..., 18)` fragment with the section that actually matched.
