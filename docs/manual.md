---
title: LLM Wiki 매뉴얼
tags:
  - manual
  - llm-wiki
  - runbook
---
# LLM Wiki 매뉴얼

LLM Wiki는 Codex를 비롯한 LLM 에이전트를 위한 로컬 우선(local-first) 지식 베이스다.
승인된 Markdown 지식을 저장하고, SQLite FTS5로 색인하며, CLI를 통해
출처에 근거한 컨텍스트를 반환한다.

페이지 목록은 [[index]]에서 시작하거나, [[example]] 아키텍처 가이드를 읽는다.
Hook 설계 규칙은 [[decisions/hook-event-name-invariant]]에 있다.

## 1. 전역 위키 초기화

CLI를 한 번 설치한다:

```bash
uv tool install git+https://github.com/tnqkr3753/llm-wiki.git
```

그다음 공통 위키를 준비한다:

```bash
llm-wiki init
```

이 명령은 다음을 생성한다:

```text
~/.llm-wiki/wiki.db
~/.llm-wiki/config.toml
~/.llm-wiki/docs/index.md
~/.llm-wiki/docs/decisions/
~/.llm-wiki/docs/runbooks/
~/.llm-wiki/docs/references/
```

필요하면 별도의 공통 저장소를 지정할 수 있다:

```bash
llm-wiki init --home /path/to/common/wiki
```

`LLM_WIKI_HOME=/path/to/common/wiki`를 설정해 두면 이후 명령이 기본적으로
그 홈을 사용하도록 할 수도 있다.

## 2. 프로젝트 초기화

다른 프로젝트를 준비한다:

```bash
llm-wiki project init -p /path/to/project
```

이 명령은 다음을 생성한다:

```text
.llm-wiki/wiki.db
.llm-wiki/config.toml
docs/index.md
docs/decisions/
docs/runbooks/
docs/references/
```

대상 프로젝트가 Codex에게 위키 조회 방법을 알려줘야 한다면 `--agents`를 사용한다:

```bash
llm-wiki project init -p /path/to/project --agents
```

그러면 `ask-context`와 `add` 명령이 담긴 `AGENTS.md` 스니펫이 작성된다.

## 3. 영속 지식 추가

`docs/` 아래에 frontmatter가 있는 Markdown 문서를 만든다:

```markdown
---
title: Deployment Runbook
tags: runbook, deployment
---

Restart the worker after changing queue settings.
```

색인한다:

```bash
llm-wiki add docs/runbooks/deployment.md
```

## 4. 컨텍스트 조회

사람이 직접 검색하려면:

```bash
llm-wiki search deployment
```

Codex나 다른 LLM에 전달할 컨텍스트를 준비하려면:

```bash
llm-wiki ask-context "How do we deploy?"
```

출력은 에이전트 프롬프트에 그대로 붙여넣을 수 있도록 의도적으로 일반 텍스트다.

### 태그로 범위 지정

LLM Wiki는 하나로 연결된 지식 그래프이므로, 권장 구성은 데이터베이스를 여러 개로
분리하는 대신 프로젝트별 문서에 `project:<name>` 태그를 붙인 단일 전역 위키다
(`docs/decisions/single-global-wiki-tag-scope.md` 참조).
`--tag`를 사용하면 주어진 모든 태그를 가진 문서로 검색 범위를 좁힌다
(정확 일치, 반복 지정 가능):

```bash
llm-wiki search deployment --tag project:my-app
llm-wiki ask-context "How do we deploy?" --tag project:my-app --tag runbook
```

`--tag`가 없으면 그래프 전체를 대상으로 조회한다.

## 5. 경로 해석

색인을 읽거나 쓰는 모든 명령은 SQLite 데이터베이스를 다음 순서로 해석한다:

```text
1. --db /path/to/wiki.db
2. LLM_WIKI_DB=/path/to/wiki.db
3. nearest project .llm-wiki/config.toml db_path
4. LLM_WIKI_HOME/config.toml db_path, or ~/.llm-wiki/config.toml db_path
5. ~/.llm-wiki/wiki.db
```

일회성 명령에는 `--db`, 임시 셸 세션에는 `LLM_WIKI_DB`, 프로젝트 위키에는
프로젝트의 `.llm-wiki/config.toml`, 공유 공통 저장소에는 `LLM_WIKI_HOME`을
사용한다.

프로젝트 설정 탐색은 명령의 현재 작업 디렉터리에서 시작한다. Codex가
`uv run --directory /path/to/llm-wiki`를 통해 CLI를 실행한다면, 생성된
`AGENTS.md`에 명시적인 프로젝트 `--db` 인자를 유지한다.

## 6. Codex 연동

LLM Wiki Codex 스킬을 한 번 설치한다:

```bash
llm-wiki codex install-skill
```

기본적으로 생성된 `SKILL.md` 파일들이 `~/.agents/skills/llm-wiki-*` 아래에
작성된다. 다른 Codex 스킬 디렉터리를 쓰려면 `--skills-dir <path>`를, 기존
생성 스킬을 교체하려면 `--force`를 사용한다.

생성되는 스킬 언어의 기본값은 `--language auto`다. auto 모드는 `LC_ALL`,
`LC_MESSAGES`, `LANG`이 한국어를 가리키면 이를 따르고, 그렇지 않으면 영어로
폴백한다. 생성 스킬 언어를 명시하려면 `--language ko` 또는 `--language en`을
사용한다:

```bash
llm-wiki codex install-skill --language ko
```

설치되는 Codex 스킬:

| 스킬 | 설치되는 Markdown | 설명 |
|---|---|---|
| `llm-wiki-init` | `~/.agents/skills/llm-wiki-init/SKILL.md` | LLM Wiki를 전역 또는 프로젝트에 설정할 때 사용한다. 저장소, docs 폴더, 프로젝트 로컬 `AGENTS.md` 지침을 초기화하여 Codex가 올바른 위키 DB를 조회할 수 있게 한다. |
| `llm-wiki-recall` | `~/.agents/skills/llm-wiki-recall/SKILL.md` | 답이 이전 결정, 프로젝트 규칙, runbook, 아키텍처, 구현 맥락에 좌우되는 프로젝트별 또는 공유 맥락 작업 전에 사용한다. 이 스킬은 프로젝트 지침/설정을 읽고 `llm-wiki ask-context`를 실행하며, Codex에게 위키 근거 사실과 추론을 구분하도록 요청한다. |
| `llm-wiki-promote` | `~/.agents/skills/llm-wiki-promote/SKILL.md` | 안정된 지식을 영속적인 위키 콘텐츠로 만들어야 할 때 사용한다. 알맞은 docs 폴더 아래에 Markdown을 작성하거나 갱신하고, `llm-wiki add`로 색인한 뒤, 조회(recall)를 검증한다. |
| `llm-wiki-maintain` | `~/.agents/skills/llm-wiki-maintain/SKILL.md` | LLM Wiki 프로젝트나 전역 홈을 점검, 복구, 재색인하거나 최신성을 확인할 때 사용한다. 안전하게 검사하고, Markdown을 재색인하며, config/AGENTS.md 연결을 확인하고, 결과를 보고한다. |
| `llm-wiki-hooks` | `~/.agents/skills/llm-wiki-hooks/SKILL.md` | LLM Wiki용 프로젝트 로컬 Codex hook을 설치하거나 검증할 때 사용한다. `llm-wiki codex install-hooks`를 실행하고, 생성된 `UserPromptSubmit` hook을 확인하며, `/hooks`에서 신뢰(trust)하도록 사용자에게 안내한다. |

프로젝트가 매 프롬프트 전에 위키 컨텍스트를 자동으로 조회해야 한다면
프로젝트 로컬 Codex hook을 설치한다:

```bash
llm-wiki codex install-hooks -p /path/to/project
```

이 명령은 다음을 작성한다:

```text
/path/to/project/.codex/hooks.json
/path/to/project/.codex/hooks/llm_wiki_user_prompt.py
```

이 hook은 `UserPromptSubmit`에서 실행된다. 읽기 전용이며, 프로젝트의
`.llm-wiki/config.toml`, `LLM_WIKI_DB`, `LLM_WIKI_HOME`을 확인하고
`llm-wiki ask-context`를 실행한 뒤, 위키 컨텍스트가 존재할 때만
`additionalContext`를 반환한다. Codex는 관리 대상이 아닌 프로젝트 hook이
실행되기 전에 `/hooks`에서 검토·신뢰(trust)되기를 요구한다.

Hook 선택 기준:

- 위키 조회(recall)에는 `UserPromptSubmit`을 사용한다. 사용자 프롬프트가
  전송되기 직전에 실행되고 `additionalContext`를 추가할 수 있기 때문이다.
- `SessionStart`는 프로젝트에 LLM Wiki가 설정되어 있음을 Codex에 알리는
  등의 가벼운 시작 안내 용도로 나중에 써도 괜찮다. 아직 사용자 질문이
  없으므로 전체 검색은 피한다.
- `PreToolUse`와 `PostToolUse`는 일반적인 위키 조회가 아니라 명령·파일
  가드레일에 더 적합하다.
- 자동 승격(promotion)에 `Stop`과 `PostCompact`를 쓰지 않는다. 위키 승격은
  `llm-wiki-promote`를 통해 명시적으로 유지해야 한다.

LLM Wiki를 사용해야 하는 각 프로젝트마다 다음을 실행한다:

```bash
uv run llm-wiki project init -p /path/to/project --agents
```

생성된 `AGENTS.md`는 Codex에게 다음을 호출하도록 지시한다:

```bash
uv run --directory /path/to/llm-wiki llm-wiki ask-context "<question>" --db /path/to/project/.llm-wiki/wiki.db
```

Codex가 검토된 문서를 같은 프로젝트 위키로 승격할 때도 프로젝트 로컬
데이터베이스를 명시적으로 전달해야 한다:

```bash
uv run --directory /path/to/llm-wiki llm-wiki add /path/to/project/docs/<file>.md --db /path/to/project/.llm-wiki/wiki.db
```

프로젝트 특화 질문에 답하거나 기존 결정에 의존하는 변경을 하기 전에
이렇게 한다.

전역/공통 지식에는 동일한 `llm-wiki-promote` 스킬을 사용한다. Markdown
파일을 `~/.llm-wiki/docs/decisions/`, `~/.llm-wiki/docs/runbooks/`,
`~/.llm-wiki/docs/references/` 아래에 작성한 뒤, CLI가 전역 DB를 해석하게
둔다:

```bash
uv run --directory /path/to/llm-wiki llm-wiki add ~/.llm-wiki/docs/references/example.md
uv run --directory /path/to/llm-wiki llm-wiki ask-context "example"
```

공통 위키가 다른 곳에 있다면 `LLM_WIKI_HOME=/path/to/common/wiki`를 설정하고
`$LLM_WIKI_HOME/docs/` 아래에 작성한다.

## 7. Claude Code 연동

같은 다섯 가지 LLM Wiki 스킬을 Claude Code용으로 설치한다:

```bash
llm-wiki claude install-skill
```

기본적으로 생성된 `SKILL.md` 파일들이 `~/.claude/skills/llm-wiki-*` 아래에
작성된다. `--skills-dir`, `--tool-path`, `--language`, `--force` 옵션은
Codex 설치기와 정확히 동일하게 동작한다.

프로젝트 로컬 Claude Code hook을 설치한다:

```bash
llm-wiki claude install-hooks -p /path/to/project
```

이 명령은 다음을 작성한다:

```text
/path/to/project/.claude/settings.json
/path/to/project/.claude/hooks/llm_wiki_user_prompt.py
```

이 hook은 `.claude/settings.json`의 `hooks.UserPromptSubmit` 섹션에
병합되며, 해당 파일의 다른 설정은 보존된다. Codex hook과 마찬가지로
읽기 전용이고, 위키 컨텍스트가 존재할 때만 `additionalContext`를 추가한다.
Claude Code는 앱 외부에서 변경된 hook이 실행되기 전에 `/hooks`에서
검토되기를 요구한다.

## 8. Gemini CLI 연동

같은 다섯 가지 LLM Wiki 스킬을 Gemini CLI용으로 설치한다:

```bash
llm-wiki gemini install-skill
```

기본적으로 생성된 `SKILL.md` 파일들이 `~/.gemini/skills/llm-wiki-*` 아래에
작성된다. Gemini CLI는 동일한 `SKILL.md` 형식을 읽으므로, 옵션과 생성
콘텐츠는 다른 설치기와 동일하다.

프로젝트 로컬 Gemini CLI hook을 설치한다:

```bash
llm-wiki gemini install-hooks -p /path/to/project
```

이 명령은 다음을 작성한다:

```text
/path/to/project/.gemini/settings.json
/path/to/project/.gemini/hooks/llm_wiki_user_prompt.py
```

Gemini CLI에는 `UserPromptSubmit` 이벤트가 없다. 대응되는 이벤트는
제출된 프롬프트를 에이전트가 처리하기 직전에 실행되는 `BeforeAgent`다.
이 hook은 `.gemini/settings.json`의 `hooks.BeforeAgent` 섹션에 5000 ms
타임아웃(Gemini hook 타임아웃은 밀리초 단위)으로 병합되며, 해당 파일의
다른 설정은 보존된다. 설치 후에는 설정이 다시 로드되도록 Gemini CLI를
재시작하고, 프롬프트가 뜨면 프로젝트 폴더를 신뢰(trust)한다.

## 9. Agent Memory 이관

Agent Memory는 임시 작업 관찰과 세션 회상에 유용하다. LLM Wiki는
영속적이고 검토된 지식을 위한 것이다. 어떤 관찰이 안정된 규칙, runbook,
결정, 참조가 되면 `docs/` 아래에 Markdown 문서를 작성하고 `llm-wiki add`로
색인하여 승격한다.

권장 흐름:

```text
Agent Memory observation
-> human or agent reviews it
-> Markdown document under docs/
-> llm-wiki add
-> future Codex sessions retrieve it with ask-context
```
