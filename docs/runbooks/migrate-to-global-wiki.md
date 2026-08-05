---
title: 프로젝트별 위키를 전역 위키로 이관하기
tags:
  - runbook
  - llm-wiki
  - migration
---
# 프로젝트별 위키를 전역 위키로 이관하기

프로젝트마다 별도의 `.llm-wiki/wiki.db`를 구성해 사용하다가,
[[decisions/single-global-wiki-tag-scope]]에서 설명하는 단일 연결 그래프로
전환하려는 사용자를 위한 문서다. [[index]]로 돌아가기. 조회 관련 플래그는
[[manual]]에 있다.

여기서 강제되는 것은 없다. 프로젝트별 데이터베이스는 `mode = "isolated"`로
계속 동작한다. 여러 개의 고립된 색인 대신 `project:` 태그로 범위를 나누는
하나의 그래프를 원할 때만 이관한다.

## 프로젝트 설정

새 프로젝트는 기본적으로 전역 위키를 사용한다. `llm-wiki project init`은
`.llm-wiki/config.toml`에 `mode = "global"`과 `project_tag`(예:
`project:evbp-etl`)를 기록하고 로컬 DB를 만들지 않는다. 기존 프로젝트는
이 키들을 추가하면 전환된다. `db_path`만 있는 레거시 설정은 그렇게 하기
전까지 isolated로 유지된다. 데이터베이스 해석 순서는 `--db` >
`LLM_WIKI_DB`(환경변수) > 프로젝트 설정(isolated 모드에 한함) > 전역 설정이다.

## 색인만 하는 옵션 — 문서는 각 저장소에 유지

각 저장소의 `docs/`를 하나의 전역 데이터베이스로 색인하면
(`llm-wiki reindex -p /path/to/my-app/docs --db ~/.llm-wiki/wiki.db`)
**CLI** 그래프는 연결된다. 그러나 Obsidian은 열린 vault 안의 파일만 보므로,
이 옵션으로는 해당 파일들이 전역 Graph View에 보이지 않는다. 하나의 물리적
vault를 원한다면 아래의 vault 실체화(materializer)를 사용한다.

## 물리적 vault 실체화 — dry-run 먼저, 그다음 적용

`llm-wiki vault import`는 승인된 Markdown 루트들을
`~/.llm-wiki/docs/projects/<slug>/` 아래의 네임스페이스 경로로 복사하고,
frontmatter에서 `tags` 필드만 정규화하며(`project:<slug>` 추가), 프로젝트
허브로의 관리형(managed) backlink를 삽입하고, 모든 허브를 전역 index에서
링크한다. 원본 파일은 절대 수정·이동·삭제되지 않는다.

다음 순서로 실행한다:

1. **백업** — 전역 docs와 건드리는 모든 DB를 백업한다(docs는 `rsync`,
   데이터베이스는 `sqlite3 ... ".backup ..."`).
2. **Dry-run** — 승인된 모든 소스 루트를 지정해 실행한다:

   ```bash
   llm-wiki vault import \
     --source evbp-etl=/Users/yuntaepark/Work/evbp-etl/docs \
     --source evbp-etl-dbt=/Users/yuntaepark/Work/evbp-etl-dbt/docs \
     --home ~/.llm-wiki
   ```

   계획(plan)에는 create/update/unchanged/conflict/skipped 개수가 나온다.
   이미 존재하지만 이전 import manifest가 소유하지 않은 대상은
   **conflict**이며, import는 덮어쓰기를 거부한다. 소스 루트를 벗어나는
   심볼릭 링크는 건너뛰고 이름이 표시된다.
3. **적용** — dry-run이 conflict 0건을 보고할 때만, 같은 명령에 `--apply`를
   붙여 다시 실행한다. 전환 전후로 JSON manifest(소스, 해시, 액션)가
   `~/.llm-wiki/migrations/` 아래에 기록된다.
4. **새 DB 재구축** — 기존 멀티 루트 DB를 정리(prune)하는 대신 물리적
   vault로부터 새 DB를 만든다:

   ```bash
   llm-wiki reindex -p ~/.llm-wiki/docs --db ~/.llm-wiki/wiki.next.db
   ```

   검증한 뒤, 기존 DB를 백업 디렉터리로 원자적으로 옮기고
   `wiki.next.db`를 `wiki.db`로 이름을 바꾼다.
5. **감사(audit)**:

   ```bash
   llm-wiki vault audit --home ~/.llm-wiki --db ~/.llm-wiki/wiki.db
   ```

   물리적 Markdown 개수가 색인된 개수와 같아야 하며, 외부 색인 경로 0건,
   관리형 고아(orphan) 0건, 해석되지 않는 관리형 target 0건이어야 한다.

적용 후 dry-run을 다시 실행하면 모두 `unchanged`로 보고되어야 한다 —
실체화는 멱등(idempotent)하다.

## 이관 후 조회

```bash
llm-wiki search "deploy" --project evbp-etl
llm-wiki ask-context "how do we deploy?" --project evbp-etl
llm-wiki search "deploy"          # no --project spans the whole graph
```

`--project`는 선택한 프로젝트와 전역/공통 문서를 반환하고 다른 프로젝트는
제외한다.

## 체크리스트

1. **태그 규칙** — 프로젝트 특화 문서에는 `project:<name>`을 붙이고,
   프로젝트 간 공용 지식에는 `project:` 태그를 붙이지 않는다.
2. **스킬 재설치** — 에이전트가 기본적으로 전역 DB를 해석하도록 한다:

   ```bash
   llm-wiki claude install-skill -g --force    # or codex / gemini
   ```

3. **기존 프로젝트 DB** — 보관한다. 이것이 롤백 경로다. 강한 격리가 필요한
   저장소는 `mode = "isolated"`와 로컬 `--db /path/.llm-wiki/wiki.db`를
   유지한다.
4. **롤백** — 백업해 둔 전역 docs와 DB를 복원하고, export했다면
   `unset LLM_WIKI_DB`를 실행한다. 건드리지 않은 로컬 DB들은 계속 동작한다.

## 반복 실행해도 안전

`reindex`는 **전달한 루트 안에서만** 사라진 문서를 정리하고,
`vault import`는 관리 대상이 아닌 target을 거부하므로, 어떤 단계를 다시
실행해도 멱등하며 다른 프로젝트의 지식을 삭제하지 않는다.
