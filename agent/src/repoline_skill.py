from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from model_stream import TextStreamProvider, normalize_provider

DEFAULT_REPOLINE_SKILL_NAME = "repoline-voice-session"
PROJECT_SKILL_PATHS: dict[TextStreamProvider, tuple[str, ...]] = {
    "claude": (".claude", "skills"),
    "codex": (".agents", "skills"),
}
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True, slots=True)
class RepoLineSkillPrompt:
    prompt: str
    mode: Literal["env-override", "installed", "fallback-skill", "default"]
    skill_name: str
    source_path: str | None = None


def bundled_skill_markdown_path(
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
) -> Path:
    return Path(__file__).resolve().parents[2] / "skills" / skill_name / "SKILL.md"


def installed_skill_markdown_path(
    working_directory: str | Path | None,
    provider: TextStreamProvider,
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
) -> Path | None:
    if not working_directory:
        return None

    root = Path(working_directory).expanduser()
    parts = PROJECT_SKILL_PATHS[normalize_provider(provider)]
    return root.joinpath(*parts, skill_name, "SKILL.md")


def extract_skill_body(markdown: str) -> str:
    body = _FRONTMATTER_RE.sub("", markdown, count=1)
    return body.strip()


def read_skill_body(skill_markdown_path: Path) -> str:
    markdown = skill_markdown_path.read_text(encoding="utf-8")
    return extract_skill_body(markdown)


def repoline_session_hint(skill_name: str = DEFAULT_REPOLINE_SKILL_NAME) -> str:
    return (
        "This is a RepoLine voice session. "
        f"If the repo has the `{skill_name}` skill installed, use it for spoken phrasing, "
        "tool narration, and progress updates."
    )


def resolve_repoline_skill_prompt(
    provider: TextStreamProvider,
    working_directory: str | Path | None,
    explicit_system_prompt: str | None,
    default_system_prompt: str,
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
    fallback_skill_markdown_path: Path | None = None,
) -> RepoLineSkillPrompt:
    explicit = (explicit_system_prompt or "").strip()
    if explicit:
        return RepoLineSkillPrompt(
            prompt=f"{explicit}\n\n{repoline_session_hint(skill_name)}",
            mode="env-override",
            skill_name=skill_name,
        )

    installed_path = installed_skill_markdown_path(working_directory, provider, skill_name)
    if installed_path and installed_path.is_file():
        return RepoLineSkillPrompt(
            prompt=repoline_session_hint(skill_name),
            mode="installed",
            skill_name=skill_name,
            source_path=str(installed_path),
        )

    skill_path = fallback_skill_markdown_path or bundled_skill_markdown_path(skill_name)
    if skill_path.is_file():
        skill_body = read_skill_body(skill_path)
        if skill_body:
            return RepoLineSkillPrompt(
                prompt=f"{skill_body}\n\n{repoline_session_hint(skill_name)}",
                mode="fallback-skill",
                skill_name=skill_name,
                source_path=str(skill_path),
            )

    return RepoLineSkillPrompt(
        prompt=f"{default_system_prompt.strip()}\n\n{repoline_session_hint(skill_name)}",
        mode="default",
        skill_name=skill_name,
    )
