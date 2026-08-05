---
title: Embedding 설정 표면은 백엔드보다 먼저 출시하고, 원격 엔드포인트는 opt-in
tags: llm-wiki, project, embedding, retrieval, decisions
---

# Embedding 설정 표면

검색은 SQLite FTS5(트라이그램 색인 위의 BM25)이고 당분간 그대로 유지한다.
백엔드보다 먼저 출시하는 것은 **설정 표면(configuration surface)**과
**provider 계약**뿐이다. 이렇게 하면 나중에 시맨틱 검색을 추가할 때 설정 키,
CLI 플래그, 사용자 문서를 두 번 고칠 필요가 없다.

설치된 백엔드가 없으므로 `load_provider()`는 `None`을 반환하고, 모든 검색
경로는 그대로다. 오늘 시점에 환경변수를 설정해서 바뀌는 것은 정확히 하나 —
`llm-wiki doctor`가 보고하는 내용뿐이다.

## 해석 순서

각 필드는 독립적으로 해석된다. 환경변수가 먼저이고, 그다음 가장 가까운
프로젝트 설정, 마지막이 전역 설정이다:

| 필드 | 환경변수 | 설정 (`[embedding]`) |
|---|---|---|
| model | `LLM_WIKI_EMBED_MODEL` | `model` |
| endpoint | `LLM_WIKI_EMBED_URL` | `endpoint` |
| dimension | `LLM_WIKI_EMBED_DIM` | `dimension` |
| allow remote | `LLM_WIKI_EMBED_ALLOW_REMOTE` | `allow_remote` |

필수 키는 `model`이다: 어디에도 model이 설정되어 있지 않으면 embedding은
그냥 꺼진 상태다. 필드별 해석 덕분에 프로젝트 설정에 커밋된 endpoint를
머신별로 export한 model 이름과 조합할 수 있다.

## 원격 엔드포인트는 기본 차단

위키에는 내부 결정, 런북, 원천 노트가 담긴다. 주변에 있는 `OPENAI_API_KEY`나
원격 `OLLAMA_HOST`를 자동 감지해서 문서 텍스트를 밖으로 보내는 것은 기본값으로
삼을 만한 동작이 아니다 — 실패 양상이 조용하고 되돌릴 수 없기 때문이다.
호스트가 loopback이 아닌 엔드포인트는 `LLM_WIKI_EMBED_ALLOW_REMOTE=1`
(또는 `allow_remote = true`)로 허용하지 않는 한 거부되며, `doctor`는 조용히
실패하는 대신 차단 사실을 보고한다.

## 어떤 백엔드든 선택 사항으로 남아야 한다

런타임 의존성은 typer와 rich뿐이라 `uv tool install`이 몇 초 만에 끝난다.
torch나 sentence-transformers를 필수 의존성으로 끌어들이면, 대부분의
프로젝트가 켜지도 않을 기능 때문에 수 기가바이트짜리 설치가 된다. 백엔드는
extra(`llm-wiki[embed]`) 뒤에 두고, 없을 때는 예외를 던지는 대신 BM25로
폴백해야 한다.

## 크기는 망설일 이유가 아니다

이 저장소 자체 위키(문서 7개, Markdown 20.9 KB)로 측정한 결과:

| 저장 방식 | 크기 | 원문 대비 |
|---|---|---|
| 트라이그램 FTS 색인 (현재 사용 중) | 136 KB | 6.5x |
| unicode61 FTS 색인 | 72 KB | 3.4x |
| 35 chunks x 384-dim float32 | 80 KB | 3.8x |
| 35 chunks x 384-dim int8 | 36 KB | 1.7x |

트라이그램 토크나이저가 이미 embedding보다 비싸다. 문서 1000개(~4 MB
Markdown)로 환산하면: 트라이그램 ~26 MB, 384-dim float32 chunk 5000개 ~7 MB,
int8 ~2 MB. DB가 정말 부풀어 오르는 경우는 1536-dim 벡터를 float32로 저장할
때(~29 MB)뿐인데, 이는 모델 선택의 문제지 구조 자체의 문제가 아니다.

진짜 비용은 저장이 아니라 **재계산**이다: `reindex`는 post-commit hook으로
커밋마다 도니까, 백엔드는 chunk 텍스트를 해시해서 바뀐 것만 다시 embed해야
한다.

## Chunking이 먼저다

문서 전체를 embedding하면 노력이 낭비된다 — `manual.md`에 대한 벡터 하나는
모든 것과 어렴풋이 비슷하다. 헤딩 단위 chunking이 선결 조건이며, 이는 현재의
`snippet(..., 18)` 조각을 실제로 매칭된 섹션으로 대체함으로써 BM25에서도
그 자체로 이득이 된다.
