---
title: 지식 그래프의 동작 원리
tags:
  - reference
  - graph
  - architecture
  - obsidian
---
# 지식 그래프의 동작 원리

LLM Wiki는 전문(full-text) 색인만이 아니다 — 문서들이 서로 어떻게 링크되는지도
추적하므로, 같은 Markdown 파일이 Obsidian에서는 연결된 그래프로 렌더링되고
CLI로도 조회할 수 있다. 이 페이지는 그 메커니즘을 처음부터 끝까지 설명한다.

[[index]]로 돌아가기. 사람이 따라 할 실무 절차는 [[runbooks/obsidian-usage]]
runbook에, 저장 방식의 근거는 [[example]]에 있다.

## 두 개의 계층

1. **전문 검색** — 모든 문서는 SQLite FTS5(trigram)로 색인되어
   `search` / `ask-context`에 응답한다. 이는 구조가 아니라 내용이다.
2. **링크 그래프** — 문서 본문의 모든 `[[wikilink]]`는 파싱되어 방향 간선
   (directed edge)으로 저장된다. 이는 내용이 아니라 구조다. 두 계층 모두
   같은 `wiki.db` 안에 있다.

그래프 계층이 있기에 backlink, Obsidian 그래프 뷰, `llm-wiki links`가
가능하다.

## 인식되는 wikilink 문법

파서(`markdown.parse_wikilinks`)는 문서 본문에서 target을 추출한다:

| Markdown에 쓴 형태 | 저장되는 target |
|---|---|
| `[[manual]]` | `manual` |
| `[[decisions/hook-event-name-invariant]]` | `decisions/hook-event-name-invariant` |
| `[[manual\|the CLI manual]]` (별칭) | `manual` |
| `[[manual#Setup]]` (헤딩 앵커) | `manual` |

규칙:

- `|` 뒤의 **별칭(alias)**과 `#` 뒤의 **앵커(anchor)**는 버려진다 — 링크는
  Obsidian이 해석하는 방식 그대로 문서를 가리킨다.
- Target은 **중복 제거**되고 처음 등장한 순서로 유지된다.
- 빈 target(`[[]]`)은 무시된다.
- Target은 docs 루트 기준 경로에서 `.md` 확장자를 **제외한** 것이다.

## Target이 문서로 해석되는 방식

저장된 target 문자열은 다음 순서로 실제 색인된 문서로 해석된다
(`store._resolve_target`):

1. **정확/접미 경로 일치** — 문서의 저장 경로에서 `.md`를 뺀 값이 target과
   같거나 `/<target>`으로 끝난다. 이 덕분에
   `[[decisions/hook-event-name-invariant]]`가 올바른 중첩 파일에 도달한다.
2. **파일명(basename) 일치** — 문서의 파일 stem이 target의 마지막 세그먼트와
   같아서, 단순한 `[[manual]]`이 `docs/manual.md`를 찾는다.

해석되지 않는 target(색인되지 않은 페이지로의 링크)은 결과에서 조용히
제외될 뿐 오류를 내지 않는다 — Obsidian의 "unresolved link"와 같은 방식이다.

## 저장되는 내용

`add` / `reindex`가 실행될 때마다 `upsert_document`는 `document_links`
테이블에서 해당 문서의 나가는(outgoing) 간선을 다시 쓴다:

```
document_links(source_id INTEGER, target TEXT, PRIMARY KEY(source_id, target))
```

- 링크는 추가(append)가 아니라 **교체(replace)**된다. 링크가 사라진 문서를
  재색인하면 그 간선도 제거되므로, 그래프가 파일과 어긋나는 일이 없다.
- 재색인 중 문서가 제거되면 `document_links`에서 그 문서가 source인 행도
  함께 삭제된다.
- Target은 wikilink 원문 그대로 저장되고 **조회** 시점에 해석되므로,
  target 문서를 나중에 추가하면 기존 링크가 자동으로 연결된다.

## 그래프 조회

`llm-wiki links <id>`는 양방향을 모두 보고한다:

- **Outgoing**(`store.outgoing_links`) — 이 문서에 저장된 target들을 색인된
  문서로 해석한다. 처음 등장한 순서를 유지하며, 자기 자신으로의 링크와
  해석되지 않는 target은 건너뛴다.
- **Backlinks**(`store.backlinks`) — 모든 간선을 훑어 target을 해석하고,
  그 target이 이 문서로 해석되는 source들을 수집한다.

해석 로직이 공유되기 때문에 Obsidian 그래프 뷰와 `llm-wiki links`는
어떤 간선이 존재하는지에 대해 항상 일치한다 — 단 하나의 비대칭이 있다:
SQLite 색인은 여러 루트의 문서를 담을 수 있지만, Obsidian은 열린 vault
안의 파일만 본다. 외부에서 색인된 경로는 `llm-wiki links`와 검색에는 실제
노드지만 Graph View에는 결코 나타나지 않는다. 따라서 문서를 하나의 전역
그래프에서 보이게 하려면 `~/.llm-wiki/docs` 아래에 물리적으로 실체화해야
하며([[runbooks/migrate-to-global-wiki]] 참조), `llm-wiki vault audit`이
vault 밖에 있는 색인 경로를 보고한다.

## 경로가 정규형(canonical)인 이유

모든 문서 경로는 정규형(해석 완료된 절대 경로)으로 저장된다. 그렇지 않으면
같은 파일이 `./docs/x.md`와 `/abs/docs/x.md`로 — 또는 `/tmp` 대
`/private/tmp`로 — 색인되어 중복 노드가 생기고, 한 문서의 간선이 두 행으로
쪼개진다. 정규 경로는 하나의 파일을 정확히 하나의 그래프 노드로 유지한다.
