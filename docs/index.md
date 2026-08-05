---
title: LLM Wiki 인덱스
tags:
  - index
  - llm-wiki
---

# LLM Wiki 인덱스

영속 프로젝트 지식의 진입점으로 이 페이지를 사용한다.

## 섹션

- `decisions/`: 승인된 아키텍처·제품 결정
- `runbooks/`: 반복 가능한 운영 절차
- `references/`: 안정된 원천 노트·외부 참고자료

## 페이지

- [[manual]] — 전체 CLI 매뉴얼: init, 색인, 검색, 에이전트 연동.
- [[example]] — 아키텍처 가이드: 승인된 지식이 어떻게 저장·색인되는지.
- [[runbooks/obsidian-usage]] — 이 폴더를 Obsidian으로 열기, 그래프 뷰 사용법,
  새 페이지 추가 컨벤션.
- [[runbooks/migrate-to-global-wiki]] — 프로젝트별 위키를
  `llm-wiki vault import`(dry-run 먼저)로 단일 전역 vault에 물리화하고,
  색인을 새로 만들고, `llm-wiki vault audit`로 검증하는 절차.
- [[references/knowledge-graph]] — wikilink, 링크 테이블, 해석(resolution),
  백링크가 내부에서 동작하는 방식.
- [[decisions/single-global-wiki-tag-scope]] — 프로젝트별 DB 대신 `project:`
  태그로 범위를 나누는 단일 전역 위키.
- [[decisions/hook-event-name-invariant]] — hook 이벤트명 불변식과 루프를 도는
  `Stop` hook이 없는 이유.

이 폴더를 Obsidian vault로 열면 같은 그래프를 시각적으로 탐색할 수 있다 — 위의
겹대괄호 링크 하나하나가 그래프 뷰의 엣지가 되고, 위키 엔진도
`llm-wiki links <id>`로 같은 엣지를 추적한다. 시작은
[[runbooks/obsidian-usage]] 참고.
