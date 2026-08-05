---
title: Obsidian에서 위키 탐색하기
tags:
  - runbook
  - obsidian
  - graph
---
# Obsidian에서 위키 탐색하기

위키의 `docs/` 폴더는 `[[wikilinks]]`가 포함된 일반 Markdown이므로,
내보내기나 변환 없이 [Obsidian](https://obsidian.md) vault로 바로 열린다.
이 runbook은 일상적인 사용법을 다룬다. 내부 메커니즘은
[[references/knowledge-graph]]를, 페이지 목록은 [[index]]를 참조한다.

## 1. Vault 열기

1. Obsidian에서: **Open folder as vault(폴더를 vault로 열기)**.
2. 위키의 docs 루트를 지정한다:
   - 프로젝트 위키: `/path/to/project/docs`
   - 전역 위키: `~/.llm-wiki/docs`
3. 프롬프트가 뜨면 폴더를 신뢰(trust)한다(본인의 노트다).

`.llm-wiki/wiki.db` 색인은 `docs/` 밖에 있으므로 Obsidian에는 결코 보이지
않는다.

## 2. Wikilink 켜기

Obsidian은 기본적으로 `[[page]]` 링크를 해석한다.
**Settings → Files & Links(설정 → 파일 및 링크)**에서 확인한다:

- **Use `[[Wikilinks]]`**: 켬
- **New link format(새 링크 형식)**: *Shortest path when possible(가능하면
  최단 경로)* — 여기서 target을 쓰는 방식과 일치한다. 예: `[[manual]]`,
  `[[decisions/hook-event-name-invariant]]`

## 3. 그래프 보기

- **Graph view(그래프 뷰)**(왼쪽 리본 또는 `Ctrl/Cmd+G`)는 모든 문서를
  노드로, 모든 `[[wikilink]]`를 간선으로 그린다. [[index]] 페이지가 대부분의
  페이지가 되돌아 링크하는 허브다.
- **Local graph(로컬 그래프)**(노트의 ⋮ 메뉴)는 해당 페이지의 이웃만
  보여준다.
- **Backlinks(백링크)**(오른쪽 사이드바)는 현재 페이지**로** 링크하는 모든
  페이지를 나열한다 — `llm-wiki links <id>`가 `← backlinks` 아래에 출력하는
  것과 같은 집합이다.

어떤 페이지가 고립된 점으로 보인다면 아직 `[[wikilinks]]`가 없는 것이다 —
[[index]]로 되돌아가는 링크를 하나 추가해 연결한다. 감사(audit) 목적이라면
Graph View 설정에서 **Orphans(고아)**를 켜고(**Existing files only(기존 파일만)**
와 **Tags(태그)**도 켠 상태로) 연결되지 않은 노트와 해석되지 않는 target을
한눈에 볼 수 있게 한다.

## 3b. 전역 vault의 프로젝트 허브

`llm-wiki vault import`로 프로젝트들을 전역 vault에 실체화하면
([[runbooks/migrate-to-global-wiki]] 참조), 각 프로젝트는
`projects/evbp-etl/` 같은 네임스페이스 아래에 자리한다:

- `projects/<slug>/index.md`가 **프로젝트 허브**다. 그 안의 관리형(managed)
  블록이 해당 프로젝트의 모든 import된 노트를 링크한다.
- 모든 관리형 노트는 관리형 `Related: [[projects/<slug>/index]]` backlink를
  가지므로, 관리형 노트는 고아가 되지 않는다.
- 전역 `index.md`는 모든 프로젝트 허브를 링크하는 관리형 블록을 가진다.
- 프로젝트 태그는 YAML 리스트 태그(`project:<slug>`)이므로, 쉼표로 구분된
  스칼라 하나가 아니라 Graph View에서 개별 태그 노드로 나타난다.

전체 표면은 다음으로 교차 검증한다:

```bash
llm-wiki vault audit --home ~/.llm-wiki --db ~/.llm-wiki/wiki.db
```

이 명령은 물리적 Markdown과 색인된 문서를 비교하여 고아 노드, 해석되지 않는
wikilink target, vault 밖의 색인 경로를 보고한다.

**롤백**: `~/.llm-wiki/backups/`에서 백업된 `docs/` 트리와 DB를 복원한다.
import는 원본 저장소를 절대 수정하지 않으므로 저장소 쪽 롤백은 필요 없다.

## 4. 페이지 추가 시 컨벤션

`docs/` 아래에 새 문서를 작성할 때 다음을 지켜 Obsidian과 위키 엔진을
동기화 상태로 유지한다:

1. `title`과 **YAML 리스트 태그**가 있는 **frontmatter**:

   ```markdown
   ---
   title: Deployment Rollback
   tags:
     - runbook
     - deployment
   ---
   ```

2. **그래프에 연결하기** — 새 페이지에서 최소 하나의 `[[index]]` 링크를,
   `index.md`에서 `[[your-new-page]]` 링크를 추가하여 고아 노드가 되지
   않게 한다.

3. **재색인** — 엔진이 새 간선을 저장하도록 한다:

   ```bash
   llm-wiki reindex          # whole docs root, or:
   llm-wiki add docs/runbooks/deployment-rollback.md
   ```

`llm-wiki-promote` 스킬은 지식을 위키로 승격할 때 정확히 이 컨벤션들을
자동으로 적용한다.

## 5. CLI로 그래프 교차 검증

Obsidian의 그래프는 시각적이고, 엔진의 그래프는 조회 가능하다. 둘은
일치해야 한다:

```bash
llm-wiki search "<text>"      # find a document id
llm-wiki links <id>           # → outgoing links and ← backlinks
```

Obsidian에는 보이는 간선이 `llm-wiki links`에는 없다면 색인이 오래된 것이다 —
`llm-wiki reindex`를 실행한다.
