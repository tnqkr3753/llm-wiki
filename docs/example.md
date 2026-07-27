---
title: Architecture Guide
tags:
  - architecture
  - agent-memory
  - runbook
---

LLM Wiki stores approved knowledge in Markdown and indexes it into SQLite FTS.
Agent Memory is useful for working observations, while LLM Wiki is the durable
source for reviewed project knowledge.

See [[manual]] for the full command surface, and return to the [[index]] for the
list of pages. Hook-related design constraints live in
[[decisions/hook-event-name-invariant]].
