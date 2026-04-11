from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from model_stream import TextStreamProvider, normalize_provider

DEFAULT_REPOLINE_SKILL_NAME = "repoline-voice-session"
DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME = "repoline-tts-pronunciation"
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
    tts_pronunciation_skill_name: str | None = None,
    has_tts_pronunciation_skill: bool = False,
) -> str:
    normalized_provider = normalize_provider(provider)
    voice_context_hint = (
        " The user is hearing you over a live phone call or browser voice session. "
        "Keep replies brief and easy to hear. "
        "Do not default to long bullet lists, numbered lists, or menu-style option dumps. "
        "Use one or two short sentences unless the user explicitly asks for structure. "
        "Ask at most one concise follow-up question at a time. "
        "If you narrate work, make it specific to the action you are actually taking. "
        "Do not rely on stock throat-clearing lines just to fill silence."
    )
    pronunciation_hint = ""
    if has_tts_pronunciation_skill:
        if normalized_provider == "cursor":
            pronunciation_hint = (
                " If the user says something sounded weird, was mispronounced, "
                "or got spelled out letter by letter, use the installed RepoLine TTS "
                "pronunciation rule silently and update its provider-specific notes."
            )
        elif tts_pronunciation_skill_name:
            pronunciation_hint = (
                " If the user says something sounded weird, was mispronounced, "
                f"or got spelled out letter by letter, use the `{tts_pronunciation_skill_name}` "
                "skill silently and update its provider-specific notes."
            )

    if normalized_provider == "cursor":
        return (
            "This is a RepoLine voice session. "
            f"{voice_context_hint}"
            " "
            "Use the installed RepoLine voice rule silently for spoken phrasing, "
            "tool narration, and progress updates. "
            "Do not mention the rule file or say that you are following a rule unless the user asks."
            f"{pronunciation_hint}"
        )

    return (
        "This is a RepoLine voice session. "
        f"{voice_context_hint}"
        " "
        f"Use the `{skill_name}` skill silently for spoken phrasing, "
        "tool narration, and progress updates. "
        "Do not mention the skill name or say that you are using a skill unless the user asks."
        f"{pronunciation_hint}"
    )


def resolve_repoline_skill_prompt(
    provider: TextStreamProvider,
    working_directory: str | Path,
    explicit_system_prompt: str | None,
    skill_name: str = DEFAULT_REPOLINE_SKILL_NAME,
    tts_pronunciation_skill_name: str | None = DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
) -> RepoLineSkillPrompt:
    explicit = (explicit_system_prompt or "").strip()
    has_tts_pronunciation_skill = bool(tts_pronunciation_skill_name) and (
        installed_skill_markdown_path(
            working_directory,
            provider,
            tts_pronunciation_skill_name or DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
        ).is_file()
    )
    if explicit:
        return RepoLineSkillPrompt(
            prompt=(
                f"{explicit}\n\n"
                f"{repoline_session_hint(provider, skill_name, tts_pronunciation_skill_name, has_tts_pronunciation_skill)}"
            ),
            mode="env-override",
            skill_name=skill_name,
        )

    installed_path = installed_skill_markdown_path(
        working_directory, provider, skill_name
    )
    if installed_path.is_file():
        return RepoLineSkillPrompt(
            prompt=repoline_session_hint(
                provider,
                skill_name,
                tts_pronunciation_skill_name,
                has_tts_pronunciation_skill,
            ),
            mode="installed",
            skill_name=skill_name,
            source_path=str(installed_path),
        )

    raise FileNotFoundError(
        f"RepoLine skill `{skill_name}` is not installed for {provider} in {working_directory}"
    )
