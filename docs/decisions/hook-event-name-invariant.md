---
title: Hook 이벤트명 불변식과 루프 없는 Stop hook 금지
tags:
  - llm-wiki
  - project
  - hooks
  - decisions
---
# Hook 이벤트명 불변식

[[index]]로 돌아가기. 관련: [[manual]]의 hook 설치 섹션들.

생성되는 모든 hook 스크립트가 stdout JSON에 출력하는 `hookEventName`
(`hookSpecificOutput.hookEventName`)은 **그 hook이 등록된 이벤트와
일치해야 한다** — `SessionStart`, `PreToolUse`, `UserPromptSubmit`.
에이전트 CLI들은 이를 검증해 불일치를 거부한다. 예를 들어 Claude Code는
`Hook returned incorrect event name: expected 'Stop' but got 'UserPromptSubmit'`
오류를 낸다.

## 우리가 겪은 근본 원인

`hook_templates.py`가 모든 smart-hook 스크립트를 생성할 때
`target.hook_event`를 재사용했는데, 이는 **recall** hook의 이벤트
(Claude/Codex는 `UserPromptSubmit`, Gemini는 `BeforeAgent`)다. 그래서
`SessionStart` awareness hook, `PreToolUse` guardrail hook, 그리고 예전의
`Stop` advisor hook 모두가 `hookEventName: "UserPromptSubmit"`을 출력해
거부됐다. prompt/recall hook만 우연히 일치했을 뿐이다.

## 컨벤션

각 hook 종류는 자신의 등록 이벤트를 가지며, `agents.py`의 `AgentTarget`에
단일 진실 원천으로 노출된다:

- `startup_event` → `SessionStart`
- `guardrail_event` → `PreToolUse` (Gemini는 `BeforeTool`)
- recall/prompt hook → `target.hook_event`

`hook_templates.context_output_source(target, event_name)`은 이벤트명을
명시적으로 받고, `agent_hooks.py`의 설치자들은 대응하는 `*_event`를
넘긴다. 다른 이벤트에 등록되는 hook에 `target.hook_event`를 절대
재사용하지 않는다.

참고: Gemini는 `hook_output_includes_event = False`로 설정되어
`hookEventName` 없이 `additionalContext` 페이로드만 출력하므로 이 검증에서
제외된다.

## 루프 없는 Stop hook 금지

`additionalContext`를 출력하는 `Stop` hook은 모델을 다시 깨우고, 그 모델
턴은 또 다른 `Stop`으로 끝나 hook을 다시 발화시킨다 — **무한 advisory
루프**다. 이 때문에 Stop / SessionEnd advisor hook은 완전히 제거됐다.
또한 대상들 자체의 `hook_choice_text` 안내("Do not use `Stop` to
auto-promote content into Wiki")와도 모순됐다.

**LLM Wiki로의 승격은 `llm-wiki-promote` 스킬을 통해 명시적으로 유지한다** —
Stop/SessionEnd hook으로 자동화하지 않는다.
