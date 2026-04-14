from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from model_stream import TextStreamProvider, normalize_provider

DEFAULT_REPOLINE_SKILL_NAME = "repoline-voice-session"
DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME = "repoline-tts-pronunciation"
README_CONTEXT_MAX_CHARS = 1400
PROJECT_SKILL_PATHS: dict[TextStreamProvider, tuple[str, ...]] = {
    "claude": (".claude", "skills"),
    "codex": (".agents", "skills"),
    "cursor": (".cursor", "rules"),
    "gemini": (".agents", "skills"),
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
    if normalized_provider == "cursor":
        pronunciation_hint = ""
        if has_tts_pronunciation_skill:
            pronunciation_hint = (
                " If the user says something sounded weird, was mispronounced, "
                "or got spelled out letter by letter, use the installed RepoLine TTS "
                "pronunciation rule silently and update its provider-specific notes."
            )
        return (
            "This is a RepoLine voice session. "
            "Use the installed RepoLine voice rule silently for spoken phrasing, tool narration, and progress updates. "
            "Keep replies brief and easy to hear. "
            "Use one or two short sentences unless the user explicitly asks for more structure. "
            "Ask at most one concise follow-up question at a time. "
            "Answer directly from the request and obvious repo context when you can. "
            "If you need to inspect files or run commands, say that immediately in one short sentence, then do it. "
            "Do not mention the rule file or say that you are following a rule unless the user asks."
            f"{pronunciation_hint}"
        )

    voice_context_hint = (
        " The user is hearing you over a live phone call or browser voice session. "
        "Keep replies brief and easy to hear. "
        "Do not default to long bullet lists, numbered lists, or menu-style option dumps. "
        "Use one or two short sentences unless the user explicitly asks for structure. "
        "Ask at most one concise follow-up question at a time. "
        "If you narrate work, make it specific to the action you are actually taking. "
        "Do not rely on stock throat-clearing lines just to fill silence. "
        "Answer from the current request, recent conversation, and repo context first when you can infer the answer confidently. "
        "Do not inspect the repo just to restate obvious README-level facts. "
        "If you need to inspect files or run commands, say that immediately in one short sentence like 'I need to look around for that,' then do the inspection."
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

    return (
        "This is a RepoLine voice session. "
        f"{voice_context_hint}"
        " "
        f"Use the `{skill_name}` skill silently for spoken phrasing, "
        "tool narration, and progress updates. "
        "Do not mention the skill name or say that you are using a skill unless the user asks."
        f"{pronunciation_hint}"
    )


def _find_repo_readme_path(working_directory: str | Path) -> Path | None:
    root = Path(working_directory).expanduser()
    for name in ("README.md", "README", "readme.md", "readme"):
        path = root / name
        if path.is_file():
            return path
    return None


def _sanitize_repo_context(text: str) -> str:
    cleaned_lines: list[str] = []
    in_code_block = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not line:
            continue
        if line.startswith("<") and line.endswith(">"):
            continue
        if line.startswith("<img") or line.startswith("</") or line.startswith("<p"):
            continue
        if line.startswith("!["):
            continue

        line = re.sub(r"<[^>]+>", " ", line)
        line = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = line.replace("`", "")
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*]\s+", "- ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    if len(cleaned) <= README_CONTEXT_MAX_CHARS:
        return cleaned
    truncated = cleaned[:README_CONTEXT_MAX_CHARS].rsplit("\n", 1)[0].rstrip()
    return truncated or cleaned[:README_CONTEXT_MAX_CHARS].rstrip()


def _repo_context_hint(working_directory: str | Path) -> str | None:
    readme_path = _find_repo_readme_path(working_directory)
    if readme_path is None:
        return None

    try:
        text = readme_path.read_text(encoding="utf-8")
    except OSError:
        return None

    sanitized = _sanitize_repo_context(text)
    if not sanitized:
        return None

    return f"Immediate repo context from {readme_path.name}:\n{sanitized}"


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
    repo_context_hint = (
        None if normalize_provider(provider) == "cursor" else _repo_context_hint(working_directory)
    )
    if explicit:
        prompt_sections = [
            explicit,
            repoline_session_hint(
                provider,
                skill_name,
                tts_pronunciation_skill_name,
                has_tts_pronunciation_skill,
            ),
        ]
        if repo_context_hint:
            prompt_sections.append(repo_context_hint)
        return RepoLineSkillPrompt(
            prompt="\n\n".join(prompt_sections),
            mode="env-override",
            skill_name=skill_name,
        )

    installed_path = installed_skill_markdown_path(
        working_directory, provider, skill_name
    )
    if installed_path.is_file():
        prompt_sections = [
            repoline_session_hint(
                provider,
                skill_name,
                tts_pronunciation_skill_name,
                has_tts_pronunciation_skill,
            )
        ]
        if repo_context_hint:
            prompt_sections.append(repo_context_hint)
        return RepoLineSkillPrompt(
            prompt="\n\n".join(prompt_sections),
            mode="installed",
            skill_name=skill_name,
            source_path=str(installed_path),
        )

    raise FileNotFoundError(
        f"RepoLine skill `{skill_name}` is not installed for {provider} in {working_directory}"
    )
