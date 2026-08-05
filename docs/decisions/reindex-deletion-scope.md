---
title: 삭제는 reindex가 담당하되, 재색인 대상 루트 안에서만
tags: llm-wiki, project, store, decisions
---
# Reindex 삭제 범위

`llm-wiki reindex`는 인덱스를 파일시스템과 일치시키는 단일 명령이다.
루트 아래의 모든 Markdown 파일을 다시 파싱하고 **원본 파일이 사라진
인덱스 항목을 제거한다**. 이전에는 `reindex_directory()`가 upsert만
수행해서 삭제되거나 이름이 바뀐 문서가 영원히 남아 있었고,
`ask-context`가 더 이상 존재하지 않는 파일을 답변의 근거로 삼을 수
있었다.

## 삭제 규칙

저장된 문서는 다음 조건이 모두 성립할 때에만 인덱스에서 삭제된다:

1. 저장된 경로가 **절대경로**이고,
2. 재색인 중인 **루트 아래**에 있으며,
3. 디스크에 파일이 **존재하지 않는다**.

규칙 1과 2가 있는 이유는 하나의 데이터베이스가 여러 루트 — 전역 홈
(`~/.llm-wiki/docs`)과 임의 개수의 프로젝트 — 를 색인할 수 있기 때문이다.
한 프로젝트를 재색인하는 작업이 다른 루트의 문서를 쫓아내서는 절대 안
된다. (초기의 `llm-wiki add docs/foo.md` 실행에서 온) 상대경로로 저장된
경로는 결코 stale로 취급하지 않는다. 알 수 없는 작업 디렉터리 기준으로
색인된 것이라 부재를 증명할 수 없기 때문이다. `reindex_directory()`는
항상 절대경로를 기록하므로, 재실행하면 인덱스는 절대경로로 수렴한다.

## 실패는 보고되며, 절대 삼켜지지 않는다

파싱 실패는 예전에는 맨 `except Exception: pass`로 버려졌다. 이제
`ReindexResult`가 `indexed`, `removed`, 그리고 `failures` 튜플을 담고,
CLI는 실패한 모든 경로를 출력하며 0이 아닌 종료 코드로 끝난다.
`parse_markdown_file()`은 OS 오류뿐 아니라 잘못된 UTF-8에 대해서도
`DocumentReadError`를 던지므로, 손상된 파일은 인덱스에서 조용히 빠지는
대신 표면화된다.

## Hook 계약

`llm-wiki git-hook install`이 설치하는 Git `post-commit` hook은
`llm-wiki reindex`를 호출하고 모든 출력을 `/dev/null`로 리다이렉트한다.
**생성된 hook이 참조하는 모든 명령은 CLI에 존재해야 한다** — 오타나
이름이 바뀐 명령은 매 커밋마다 조용히 실패한다. `test_reindex.py`가
생성된 hook 스크립트를 파싱해 거기서 호출하는 모든 `llm-wiki <command>`가
Typer 앱에 등록되어 있는지 단언함으로써 이를 강제한다.
