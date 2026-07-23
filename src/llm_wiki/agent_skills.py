"""Agent skill installation support."""

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from llm_wiki.agents import TOOL_REPO_PATH, AgentTarget
from llm_wiki.skill_templates import SkillSpec, skill_specs


class SkillLanguage(StrEnum):
    """Language mode for generated skill Markdown."""

    AUTO = "auto"
    EN = "en"
    KO = "ko"


@dataclass(frozen=True, slots=True)
class SkillInstallResult:
    """Result of installing or preserving an agent skill."""

    skill_name: str
    skill_path: Path
    installed: bool


def install_agent_skills(
    target: AgentTarget,
    skills_dir: Path | None = None,
    project_path: Path | None = None,
    tool_path: Path | None = None,
    force: bool = True,
    language: SkillLanguage = SkillLanguage.AUTO,
) -> tuple[SkillInstallResult, ...]:
    """Install LLM Wiki skills globally, into a project, or into a specific skills dir."""
    resolved_skills_dir = _resolve_skills_dir(target, skills_dir, project_path)
    resolved_tool_path = TOOL_REPO_PATH if tool_path is None else tool_path
    resolved_language = _resolve_language(language)
    return tuple(
        _install_skill(
            skills_dir=resolved_skills_dir,
            tool_path=resolved_tool_path.resolve(),
            spec=spec,
            force=force,
            language=resolved_language,
        )
        for spec in skill_specs(target)
    )


def _install_skill(
    skills_dir: Path,
    tool_path: Path,
    spec: SkillSpec,
    force: bool,
    language: SkillLanguage,
) -> SkillInstallResult:
    skill_path = skills_dir / spec.name / "SKILL.md"
    if skill_path.exists() and not force:
        return SkillInstallResult(
            skill_name=spec.name,
            skill_path=skill_path,
            installed=False,
        )

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    _ = skill_path.write_text(
        _skill_text(spec, tool_path, language),
        encoding="utf-8",
    )
    return SkillInstallResult(
        skill_name=spec.name,
        skill_path=skill_path,
        installed=True,
    )


def uninstall_agent_skills(
    target: AgentTarget,
    skills_dir: Path | None = None,
    project_path: Path | None = None,
    is_global: bool = False,
) -> tuple[Path, ...]:
    """Uninstall LLM Wiki skills from global home, a project, or a specific skills dir."""
    if is_global:
        resolved_dir = target.default_skills_dir.expanduser().resolve()
    else:
        resolved_dir = _resolve_skills_dir(target, skills_dir, project_path)

    removed: list[Path] = []
    for spec in skill_specs(target):
        skill_file = resolved_dir / spec.name / "SKILL.md"
        skill_dir = resolved_dir / spec.name
        if skill_file.exists():
            skill_file.unlink()
            removed.append(skill_file)
        if skill_dir.exists() and not any(skill_dir.iterdir()):
            skill_dir.rmdir()
    return tuple(removed)


def _resolve_skills_dir(
    target: AgentTarget,
    skills_dir: Path | None,
    project_path: Path | None = None,
) -> Path:
    if skills_dir is not None:
        return skills_dir.expanduser().resolve()
    if project_path is not None:
        return (project_path.expanduser().resolve() / target.hook_dir_name / "skills")
    return target.default_skills_dir.expanduser().resolve()


def _resolve_language(language: SkillLanguage) -> SkillLanguage:
    match language:
        case SkillLanguage.EN | SkillLanguage.KO:
            return language
        case SkillLanguage.AUTO:
            return _language_from_locale()


def _language_from_locale() -> SkillLanguage:
    locale_text = " ".join(
        os.environ.get(name, "") for name in ("LC_ALL", "LC_MESSAGES", "LANG")
    ).lower()
    if "ko" in locale_text or "kr" in locale_text:
        return SkillLanguage.KO
    return SkillLanguage.EN


def _language_policy(language: SkillLanguage) -> str:
    if language is SkillLanguage.KO:
        return """## 언어 정책

- 사용자의 언어와 프로젝트 문서에서 주로 쓰는 언어를 따릅니다.
- 한국어 맥락에서는 답변, 생성 문서, 요약을 한국어로 작성합니다.
- 위키 근거와 추론을 구분해서 말합니다.
"""
    return """## Language Policy

- Follow the user's language and the dominant language of the project docs.
- Do not force English when the user or project is using Korean.
- Separate wiki-grounded facts from inference.
"""


def _skill_text(
    spec: SkillSpec,
    tool_path: Path,
    language: SkillLanguage,
) -> str:
    body = spec.body_template.format(tool_path=tool_path)
    description = (
        spec.korean_description if language is SkillLanguage.KO else spec.description
    )
    return f"""---
name: {spec.name}
description: {description}
---

{_language_policy(language)}

{body}
"""
