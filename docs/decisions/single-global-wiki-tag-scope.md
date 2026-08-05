---
title: 하나의 전역 위키, 프로젝트 태그로 범위 구분
tags:
  - decisions
  - llm-wiki
  - graph
---
# 하나의 전역 위키, 프로젝트 태그로 범위 구분

영속 지식의 기본 보금자리는 **단일 전역 위키**(`~/.llm-wiki`, 또는
`$LLM_WIKI_HOME`)다. 프로젝트별 지식은 프로젝트별 개별 데이터베이스가
**아니라** `project:<name>` 태그로 구분한다.

[[index]]로 돌아가기. 검색 표면은 [[manual]]에, 그래프 메커니즘은
[[references/knowledge-graph]]에 있다.

## 이유

LLM Wiki는 지식 그래프이고, 그래프의 가치는 엣지에 있다. 지식을
프로젝트별 데이터베이스로 쪼개면 프로젝트 간 엣지가 구조적으로 불가능해진다
— 프로젝트 A의 결정이 프로젝트 B의 대응 패턴으로 절대 링크될 수 없다.
Obsidian 그래프 뷰도 서로 단절된 vault들로 파편화된다.

프로젝트별 데이터베이스의 원래 이유였던 격리는 사실 별도 데이터베이스를
요구하지 않는다. 태그와 검색 시점 필터만으로 모든 문서를 하나의 연결된
그래프에 유지하면서 동일한 분리를 얻을 수 있다.

## 컨벤션

- 영속 지식은 전역 docs 루트
  (`~/.llm-wiki/docs/{decisions,runbooks,references}/`) 아래에 작성한다.
- 프로젝트별 문서에는 종류 태그(`decision`, `runbook`, `reference`)에
  더해 `project:<name>`(예: `project:llm-wiki`) 태그를 붙인다.
- 진정한 프로젝트 횡단 지식은 `project:` 태그를 아예 생략한다.

## SQLite 그래프 대 물리적 Obsidian vault

이 둘은 서로 다른 표면이며, Obsidian에 보이는 것은 하나뿐이다:

- **SQLite 인덱스**(`~/.llm-wiki/wiki.db`)는 여러 루트의 Markdown을
  동시에 색인할 수 있다. CLI 그래프(`llm-wiki links`, 검색, 백링크)는 그
  전부를 가로질러 연결한다.
- **물리적 vault**는 폴더다. Obsidian은 열린 vault 안의 파일만 본다 —
  SQLite가 알고 있는 외부 경로는 아무리 잘 색인되어 있어도 Graph View에
  절대 나타나지 않는다.

따라서 물리적 그래프 표면은 `~/.llm-wiki/docs`다. 한 프로젝트의 문서를
하나의 Obsidian 그래프에서 보이게 하려면, `docs/projects/evbp-etl/` 같은
충돌 안전 네임스페이스로 물질화한다(예를 들어 `evbp-etl`의
`decisions/a.md`는 `~/.llm-wiki/docs/projects/evbp-etl/decisions/a.md`가
된다). frontmatter 태그는 `project:evbp-etl`. `llm-wiki vault import`가 그
물질화를 dry-run 우선으로 수행하고, `llm-wiki vault audit`은 물리적
vault, 인덱스, 링크 그래프가 일치하는지 검증한다.
[[runbooks/migrate-to-global-wiki]] 참조.

## 범위 안에서 검색하기

`--project`는 한 프로젝트의 슬라이스에 전역/공통 문서를 더해 선택한다:

```bash
llm-wiki search "deploy" --project foo
llm-wiki ask-context "how do we deploy?" --project foo --tag runbook
```

`--tag`는 여전히 주어진 모든 태그를 정확히 가진 문서로 필터링한다. 범위
옵션이 없으면 그래프 전체를 검색하는데, 그것이 핵심이다 — 하나의 위키,
하나의 그래프, 요청할 때만 범위 제한.

## 이 결정이 없애지 않는 것

프로젝트별 데이터베이스는 `--db` / 프로젝트 `.llm-wiki/config.toml`을
통해, 강한 격리가 필요한 경우(예: 인덱스를 절대 공유해서는 안 되는
클라이언트 저장소)를 위해 여전히 동작한다. 단지 더 이상 기본 경로가 아닐
뿐이다.

기존 프로젝트별 사용자는 [[runbooks/migrate-to-global-wiki]] runbook으로
이 모델로 이전할 수 있다.
