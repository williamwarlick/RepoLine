from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from model_stream import TextStreamProvider, normalize_provider

DEFAULT_REPOLINE_SKILL_NAME = "repoline-voice-session"
PROJECT_SKILL_PATHS: dict[TextStreamProvider, tuple[str, ...]] = {
    "claude": (".claude", "skills"),
    "codex": (".agents", "skills"),
    "cursor": (".cursor", "rules"),
}


@dataclass(frozen=True, slots=True)
class RepoLineSkillPrompt:
    prompt: str
    mode: Literal["env-override", "installed"]
    skill_name: str
    source_path: str | None = None


def installed_skill_markdown_path(
    working_directory: str | Path,
    provider: TextStreamProvider,
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
) -> Path:
    root = Path(working_directory).expanduser()
    normalized_provider = normalize_provider(provider)
    parts = PROJECT_SKILL_PATHS[normalized_provider]
    if normalized_provider == "cursor":
        return root.joinpath(*parts, f"{skill_name}.mdc")
    return root.joinpath(*parts, skill_name, "SKILL.md")


def repoline_session_hint(
    provider: TextStreamProvider,
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
) -> str:
    normalized_provider = normalize_provider(provider)
    if normalized_provider == "cursor":
        return (
            "This is a RepoLine voice session. "
            "Use the installed RepoLine voice rule silently for spoken phrasing, "
            "tool narration, and progress updates. "
            "Do not mention the rule file or say that you are following a rule unless the user asks."
        )

    return (
        "This is a RepoLine voice session. "
        f"Use the `{skill_name}` skill silently for spoken phrasing, "
        "tool narration, and progress updates. "
        "Do not mention the skill name or say that you are using a skill unless the user asks."
    )


def resolve_repoline_skill_prompt(
    provider: TextStreamProvider,
    working_directory: str | Path,
    explicit_system_prompt: str | None,
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
) -> RepoLineSkillPrompt:
    explicit = (explicit_system_prompt or "").strip()
    if explicit:
        return RepoLineSkillPrompt(
            prompt=f"{explicit}\n\n{repoline_session_hint(provider, skill_name)}",
            mode="env-override",
            skill_name=skill_name,
        )

    installed_path = installed_skill_markdown_path(
        working_directory, provider, skill_name
    )
    if installed_path.is_file():
        return RepoLineSkillPrompt(
            prompt=repoline_session_hint(provider, skill_name),
            mode="installed",
            skill_name=skill_name,
            source_path=str(installed_path),
        )

    raise FileNotFoundError(
        f"RepoLine skill `{skill_name}` is not installed for {provider} in {working_directory}"
    )
