"""Generated agent skill templates."""

from dataclasses import dataclass
from typing import Final

from llm_wiki.agents import AgentTarget


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """A generated agent skill specification."""

    name: str
    description: str
    korean_description: str
    body_template: str


def skill_specs(target: AgentTarget) -> tuple[SkillSpec, ...]:
    """Render the shared skill templates for one agent target."""
    context = {
        "agent": target.display_name,
        "hook_dir": target.hook_dir_name,
        "install_hooks_command": target.install_hooks_command,
        "hook_event": target.hook_event,
        "hook_config_rel": target.hook_config_rel,
        "hook_script_rel": target.hook_script_rel,
        "hook_trust_text": target.hook_trust_text,
        "hook_choice_text": target.hook_choice_text,
    }
    return tuple(
        SkillSpec(
            name=spec.name,
            description=spec.description.format(**context),
            korean_description=spec.korean_description.format(**context),
            body_template=spec.body_template.format(**context),
        )
        for spec in _TEMPLATE_SPECS
    )


_TEMPLATE_SPECS: Final[tuple[SkillSpec, ...]] = (
    SkillSpec(
        name="llm-wiki-init",
        description=(
            "Use this when a user wants to set up LLM Wiki globally or for a "
            "project, initialize wiki storage, create project-local AGENTS.md "
            "instructions, connect {agent} to a project wiki, configure "
            '~/.llm-wiki, or says phrases like "LLM Wiki 붙여줘", '
            '"init wiki", "프로젝트에 위키 세팅", "공통 위키 세팅", or '
            '"{agent}가 wiki 보게 해줘".'
        ),
        korean_description=(
            "사용자가 LLM Wiki를 전역 또는 프로젝트에 설정하거나, 위키 저장소를 "
            "초기화하거나, 프로젝트 AGENTS.md 지침을 만들거나, {agent}가 프로젝트 "
            '위키를 보게 하려 할 때 사용합니다. "LLM Wiki 붙여줘", "init wiki", '
            '"프로젝트에 위키 세팅", "공통 위키 세팅" 같은 요청을 포함합니다.'
        ),
        body_template="""# LLM Wiki Init

Use this skill to initialize either the global LLM Wiki home or a project wiki.
The goal is to leave future {agent} sessions able to retrieve the correct
durable knowledge safely.

## Workflow

1. Identify whether the user wants global setup or project-local setup.
2. For global setup, run:

```bash
uv run --directory {{tool_path}} llm-wiki init
```

3. For project setup, run:

```bash
uv run --directory {{tool_path}} llm-wiki project init -p /path/to/project --agents
```

   By default this connects the project to the **single global wiki**
   (`--db ~/.llm-wiki/wiki.db`) and writes `mode = "global"` plus a
   `project_tag` such as `project:demo-project` into
   `.llm-wiki/config.toml`. No project-local DB is created.

4. Only when a repo must never share an index, add `--isolated` to keep a
   project-local `.llm-wiki/wiki.db`.
5. Verify the config, docs folders, and any generated AGENTS.md exist.

## Verification

Use `test -f` for generated files and grep AGENTS.md for `llm-wiki ask-context`.
Global mode instructions name `--db ~/.llm-wiki/wiki.db` and a `--project`
scope; isolated mode names `--db /path/to/project/.llm-wiki/wiki.db`.

## Final Response

Report the initialized path, DB path, docs folders, and the recall command.
""",
    ),
    SkillSpec(
        name="llm-wiki-recall",
        description=(
            "Use this before project-specific or shared-context work when the "
            "user asks about previous decisions, project rules, runbooks, "
            'architecture, implementation context, "전에 어떻게 했지", '
            '"위키에서 찾아봐", "LLM Wiki 참고", or when a task depends on '
            "durable project knowledge."
        ),
        korean_description=(
            "프로젝트별 또는 공유 맥락 작업 전에 사용합니다. 사용자가 이전 결정, "
            "프로젝트 규칙, runbook, 아키텍처, 구현 맥락을 묻거나 "
            '"전에 어떻게 했지", "위키에서 찾아봐", "LLM Wiki 참고"라고 말할 때 '
            "위키 근거를 먼저 조회합니다."
        ),
        body_template="""# LLM Wiki Recall

Use this skill to retrieve durable project knowledge before answering or
changing code. Prefer approved LLM Wiki documents over chat memory when a
project has a local wiki.

## Workflow

1. Read the nearest applicable AGENTS.md from the target project.
2. Find an `llm-wiki ask-context` command and any explicit `--db` path.
3. The default is the **single global wiki**: `--db ~/.llm-wiki/wiki.db`,
   scoped by the project tag from `.llm-wiki/config.toml`. Run:

```bash
uv run --directory {{tool_path}} llm-wiki ask-context "how do we deploy?" \\
  --db ~/.llm-wiki/wiki.db --project demo-project
```

   `--project demo-project` returns that project's documents plus
   global/common documents and excludes other projects.
4. Only a project whose config says `mode = "isolated"` uses its local DB
   instead: `--db /path/to/project/.llm-wiki/wiki.db` (no `--project`).
5. Use returned context before answering or editing.

## Response Discipline

Say which Wiki source or title was used when available. Separate wiki-grounded
facts from inference, and say plainly when no context is found.
""",
    ),
    SkillSpec(
        name="llm-wiki-promote",
        description=(
            "Use this when stable knowledge from Agent Memory, a completed "
            "task, a decision, a runbook, or a repeated project explanation "
            "should be promoted into LLM Wiki."
        ),
        korean_description=(
            "Agent Memory, 완료된 작업, 결정사항, runbook, 반복 설명에서 나온 "
            "안정된 지식을 LLM Wiki로 승격해야 할 때 사용합니다."
        ),
        body_template="""# LLM Wiki Promote

Use this skill to turn a confirmed finding into durable Wiki knowledge. Promote
only stable decisions, runbooks, project conventions, source references, or
repeatable troubleshooting findings.

## Workflow

Default to the **single global wiki**. It is one connected knowledge graph;
scope by tags, not by separate databases.

Knowledge flows personal-first, then into the project repo:

0. **Capture first as a draft** when the knowledge is fresh or unreviewed.
   Write it under `~/.llm-wiki/docs/drafts/<slug>/` with the project tag
   plus a `draft` tag — it is immediately searchable (drafts rank below
   promoted documents) and syncs to your other machines via the vault git.
   When it matures, move it into the project repo's `docs/` and commit —
   that commit is what transfers the knowledge to teammates; the next
   `llm-wiki vault import` (or the post-merge sync hook) mirrors it back
   into `projects/<slug>/`, and then you delete the draft.

1. Write the document under the global docs root. Project-specific knowledge
   goes into that project's namespace, for example
   `~/.llm-wiki/docs/projects/demo-project/{{{{decisions,runbooks,references}}}}/`;
   cross-project knowledge goes into `~/.llm-wiki/docs/decisions/`,
   `.../runbooks/`, or `.../references/` (or `$LLM_WIKI_HOME/docs/` when
   `LLM_WIKI_HOME` is set).

2. Tag for scope with **YAML list tags** (Obsidian-compatible; the parser also
   accepts a legacy comma string). Add the project tag when the knowledge is
   specific to one repo; omit it when it applies to any project:

```markdown
---
title: Short Clear Title
tags:
  - decision
  - project:demo-project
---
```

3. Connect it into the graph. Add at least one `[[wikilink]]` back to the
   `[[index]]` (and to any closely related page), and a matching
   `[[your-new-doc]]` link from `index.md`, so the page is never an orphan.
   Wikilink targets are the path under `docs/` without the `.md` suffix, e.g.
   `[[decisions/deploy-rollback]]`.

4. Index it — let global config resolution pick `~/.llm-wiki/wiki.db`:

```bash
uv run --directory {{tool_path}} llm-wiki add \\
  ~/.llm-wiki/docs/references/example.md
```

   Reindex `index.md` too so the new edges are stored, or just run
   `llm-wiki reindex` over the docs root.

5. Verify: recall with
   `llm-wiki ask-context "<q>" --db ~/.llm-wiki/wiki.db --project demo-project`
   to confirm the scope filter works, and `llm-wiki links <id>` to confirm the
   graph edges.

Only fall back to a per-project database (`--db /path/.llm-wiki/wiki.db`) when a
repo genuinely must never share an index; otherwise stay in the global wiki.

## Final Response

Report the promoted file path, any `project:` tag applied, the linked
`index.md` edge, and the verified recall query.
""",
    ),
    SkillSpec(
        name="llm-wiki-maintain",
        description=(
            "Use this when the user wants to audit, repair, reindex, clean up, "
            "or check freshness of an LLM Wiki project or global home."
        ),
        korean_description=(
            "LLM Wiki 프로젝트나 전역 홈을 점검, 복구, 재색인, 정리하거나 "
            "문서 최신성을 확인해야 할 때 사용합니다."
        ),
        body_template="""# LLM Wiki Maintain

Use this skill to keep a project wiki reliable. Inspect first, reindex second,
and never delete user documents without explicit approval.

## Safe Audit

Check docs, AGENTS.md, project config, and global config:

```bash
find /path/to/project/docs -name '*.md' -type f
grep "llm-wiki ask-context" /path/to/project/AGENTS.md
test -f /path/to/project/.llm-wiki/config.toml
test -f ~/.llm-wiki/config.toml
```

## Reindex

Default to the **single global wiki**: reindex the global docs root in one
pass. This also drops index entries whose Markdown file was deleted or
renamed, and it names any file it cannot parse:

```bash
uv run --directory {{tool_path}} llm-wiki reindex -p ~/.llm-wiki/docs \\
  --db ~/.llm-wiki/wiki.db
```

For an explicitly isolated project (`mode = "isolated"`), reindex its local
layout instead: `llm-wiki reindex -p /path/to/project --db
/path/to/project/.llm-wiki/wiki.db`. Use `llm-wiki add <file>` only when
indexing a single new document. `llm-wiki vault audit` compares the physical
vault, the index, and the link graph in one report.

## Retrieval Usage

Ask which documents are actually earning their place:

```bash
uv run --directory {{tool_path}} llm-wiki usage --db ~/.llm-wiki/wiki.db
```

Documents that were never retrieved are promotion candidates that did not pay
off: either their titles and wording do not match how questions are asked, or
the knowledge was not durable enough to promote. Report them so the user can
rewrite or retire them. Never delete them yourself.

Flag missing frontmatter, empty documents, stale names, or failed recall. Do not
delete DB files or user documents unless the user explicitly asks.

## Final Report

Report checked file count, reindexed file count, removed entries, never-retrieved
documents, findings, recall verification, and confirm no files were deleted.
""",
    ),
    SkillSpec(
        name="llm-wiki-hooks",
        description=(
            "Use this when a user wants {agent} hooks for LLM Wiki, automatic "
            "wiki context injection before prompts, project-local {hook_dir} "
            "hook setup, hook trust guidance, or says phrases like "
            '"훅 만들어", "{agent} hook 붙여", "자동으로 위키 보게 해줘".'
        ),
        korean_description=(
            "사용자가 LLM Wiki용 {agent} hook을 설치하거나, 프롬프트 전에 위키 "
            "컨텍스트를 자동 주입하거나, 프로젝트 {hook_dir} hook 설정과 trust "
            '절차를 원할 때 사용합니다. "훅 만들어", "{agent} hook 붙여", '
            '"자동으로 위키 보게 해줘" 같은 요청을 포함합니다.'
        ),
        body_template="""# LLM Wiki Hooks

Use this skill to install and verify project-local {agent} hooks for LLM Wiki.
Hooks are opt-in per project because they run automatically in the {agent} loop.

## Workflow

1. Identify the target project directory.
2. Install the hook:

```bash
uv run --directory {{tool_path}} {install_hooks_command} -p /path/to/project
```

3. Verify generated files:

```bash
test -f /path/to/project/{hook_config_rel}
test -f /path/to/project/{hook_script_rel}
grep "{hook_event}" /path/to/project/{hook_config_rel}
grep "llm-wiki ask-context" /path/to/project/{hook_script_rel}
```

4. {hook_trust_text}

## Behavior

The generated hook runs on `{hook_event}`. It is read-only: the installer
resolves the project's wiki scope once and embeds explicit arguments, so a
global-mode project runs `llm-wiki ask-context --db ~/.llm-wiki/wiki.db
--project <slug>` without depending on shell startup files, and an isolated
project passes its local `--db`. It returns `additionalContext` only when
context exists.

## Hook Choice

{hook_choice_text}

Do not install global hooks by default. Do not auto-promote content from hooks.

## Final Response

Report the project path, generated `{hook_config_rel}`, generated script path,
and any remaining trust or approval step.
""",
    ),
)
