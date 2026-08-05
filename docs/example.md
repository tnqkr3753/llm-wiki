---
title: 아키텍처 가이드
tags:
  - architecture
  - agent-memory
  - runbook
---
LLM Wiki는 승인된 지식을 Markdown으로 저장하고 SQLite FTS로 색인한다.
Agent Memory는 작업 중의 관찰 기록에 유용하고, LLM Wiki는 검토된 프로젝트
지식의 영속적인 원천이다.

전체 명령 표면은 [[manual]]을 보고, 페이지 목록은 [[index]]로 돌아가면
된다. Hook 관련 설계 제약은 [[decisions/hook-event-name-invariant]]에
있다.
