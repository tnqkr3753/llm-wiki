"""Codex skill installation support."""

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from llm_wiki.codex_templates import SKILL_SPECS, SkillSpec

DEFAULT_CODEX_SKILLS_DIR: Final = Path("~/.agents/skills")
TOOL_REPO_PATH: Final = Path(__file__).resolve().parents[2]


class CodexSkillLanguage(StrEnum):
    """Language mode for generated Codex skill Markdown."""

    AUTO = "auto"
    EN = "en"
    KO = "ko"


@dataclass(frozen=True, slots=True)
class SkillInstallResult:
    """Result of installing or preserving a Codex skill."""

    skill_name: str
    skill_path: Path
    installed: bool

def install_codex_skill(
    skills_dir: Path | None,
    tool_path: Path | None,
    force: bool,
    language: CodexSkillLanguage,
) -> tuple[SkillInstallResult, ...]:
    """Install all LLM Wiki Codex skills into a Codex skills directory."""
    resolved_skills_dir = _resolve_skills_dir(skills_dir)
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
        for spec in SKILL_SPECS
    )


def _install_skill(
    skills_dir: Path,
    tool_path: Path,
    spec: SkillSpec,
    force: bool,
    language: CodexSkillLanguage,
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


def _resolve_skills_dir(skills_dir: Path | None) -> Path:
    if skills_dir is not None:
        return skills_dir.expanduser()
    return DEFAULT_CODEX_SKILLS_DIR.expanduser()


def _resolve_language(language: CodexSkillLanguage) -> CodexSkillLanguage:
    match language:
        case CodexSkillLanguage.EN | CodexSkillLanguage.KO:
            return language
        case CodexSkillLanguage.AUTO:
            return _language_from_locale()


def _language_from_locale() -> CodexSkillLanguage:
    locale_text = " ".join(
        os.environ.get(name, "") for name in ("LC_ALL", "LC_MESSAGES", "LANG")
    ).lower()
    if "ko" in locale_text or "kr" in locale_text:
        return CodexSkillLanguage.KO
    return CodexSkillLanguage.EN


def _language_policy(language: CodexSkillLanguage) -> str:
    if language is CodexSkillLanguage.KO:
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
    language: CodexSkillLanguage,
) -> str:
    body = spec.body_template.format(tool_path=tool_path)
    description = (
        spec.korean_description
        if language is CodexSkillLanguage.KO
        else spec.description
    )
    return f"""---
name: {spec.name}
description: {description}
---

{_language_policy(language)}

{body}
"""
