---
title: Hook event-name invariant and no looping Stop hooks
tags:
  - llm-wiki
  - project
  - hooks
  - decisions
---

# Hook event-name invariant

Back to the [[index]]. Related: the [[manual]] hook-installation sections.

Every generated hook script's `hookEventName` in its stdout JSON
(`hookSpecificOutput.hookEventName`) **must match the event the hook is
registered under** — `SessionStart`, `PreToolUse`, or `UserPromptSubmit`.
Agent CLIs validate this and reject a mismatch, e.g. Claude Code errors with
`Hook returned incorrect event name: expected 'Stop' but got 'UserPromptSubmit'`.

## Root cause we hit

`hook_templates.py` generated every smart-hook script by reusing
`target.hook_event`, which is the **recall** hook's event
(`UserPromptSubmit` for Claude/Codex, `BeforeAgent` for Gemini). So the
`SessionStart` awareness hook, the `PreToolUse` guardrail hook, and the former
`Stop` advisor hook all emitted `hookEventName: "UserPromptSubmit"` and were
rejected. Only the prompt/recall hook happened to match.

## Convention

Each hook kind has its own registered event, exposed as the single source of
truth on `AgentTarget` in `agents.py`:

- `startup_event` → `SessionStart`
- `guardrail_event` → `PreToolUse` (`BeforeTool` for Gemini)
- recall/prompt hook → `target.hook_event`

`hook_templates.context_output_source(target, event_name)` takes the event name
explicitly; installers in `agent_hooks.py` pass the matching `*_event`. Never
reuse `target.hook_event` for a hook registered under a different event.

Note: Gemini sets `hook_output_includes_event = False`, so it emits a bare
`additionalContext` payload with no `hookEventName` and is exempt from this
validation.

## No looping Stop hooks

A `Stop` hook that emits `additionalContext` re-wakes the model; that model
turn ends in another `Stop`, which fires the hook again — an **unbounded
advisory loop**. For this reason the Stop / SessionEnd advisor hook was
removed entirely. It also contradicted the targets' own `hook_choice_text`
guidance ("Do not use `Stop` to auto-promote content into Wiki").

**Promotion to LLM Wiki stays explicit** through the `llm-wiki-promote` skill —
never automated via a Stop/SessionEnd hook.
