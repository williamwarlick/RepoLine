from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any, Literal

TextStreamProvider = Literal["claude", "codex", "cursor"]
AccessPolicy = Literal["readonly", "workspace-write", "owner"]
ArtifactKind = Literal["tool", "code", "diff"]

SENTENCE_END_RE = re.compile(r"(.+?[.!?](?:['\"])?(?:\s+|$))", re.DOTALL)
FENCED_CODE_BLOCK_RE = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
PATCH_BLOCK_RE = re.compile(r"(\*\*\* Begin Patch.*?\*\*\* End Patch)", re.DOTALL)

ACCESS_POLICY_ALIASES = {
    "read-only": "readonly",
    "read_only": "readonly",
    "readonly": "readonly",
    "workspace-write": "workspace-write",
    "workspace_write": "workspace-write",
    "workspace": "workspace-write",
    "write": "workspace-write",
    "owner": "owner",
}


class TextStreamError(RuntimeError):
    """Raised when the configured CLI exits before producing usable speech text."""


@dataclass(frozen=True, slots=True)
class TextStreamConfig:
    prompt: str
    provider: TextStreamProvider = "claude"
    session_id: str | None = None
    resume_session_id: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    working_directory: str | None = None
    chunk_chars: int = 140
    access_policy: AccessPolicy = "readonly"


@dataclass(frozen=True, slots=True)
class UiArtifact:
    kind: ArtifactKind
    title: str
    text: str
    language: str | None = None
    artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class TextStreamEvent:
    type: Literal["status", "speech_chunk", "artifact", "error", "done"]
    message: str | None = None
    text: str | None = None
    final: bool = False
    exit_code: int | None = None
    session_id: str | None = None
    artifact: UiArtifact | None = None


class SentenceChunker:
    def __init__(self, chunk_chars: int) -> None:
        self.buffer = ""
        self.chunk_chars = chunk_chars

    def feed(self, text: str) -> list[str]:
        if not text:
            return []

        self.buffer += text
        chunks: list[str] = []

        while True:
            match = SENTENCE_END_RE.match(self.buffer)
            if not match:
                break
            chunk = match.group(1).strip()
            if chunk:
                chunks.append(chunk)
            self.buffer = self.buffer[match.end() :]

        while len(self.buffer) >= self.chunk_chars:
            split_at = self.buffer.rfind(" ", 0, self.chunk_chars)
            if split_at <= 0:
                split_at = self.chunk_chars
            chunk = self.buffer[:split_at].strip()
            if chunk:
                chunks.append(chunk)
            self.buffer = self.buffer[split_at:].lstrip()

        return chunks

    def flush(self) -> list[str]:
        if not self.buffer.strip():
            return []
        chunk = self.buffer.strip()
        self.buffer = ""
        return [chunk]


def normalize_provider(value: str | None) -> TextStreamProvider:
    normalized = (value or "claude").strip().lower()
    if normalized == "cursor-agent":
        normalized = "cursor"
    if normalized not in {"claude", "codex", "cursor"}:
        raise ValueError(f"unsupported bridge provider: {value}")
    return normalized  # type: ignore[return-value]


def normalize_access_policy(value: str | None) -> AccessPolicy:
    normalized = (value or "readonly").strip().lower()
    if normalized not in ACCESS_POLICY_ALIASES:
        raise ValueError(f"unsupported bridge access policy: {value}")
    return ACCESS_POLICY_ALIASES[normalized]  # type: ignore[return-value]


def infer_access_policy(
    provider: TextStreamProvider,
    explicit_policy: str | None = None,
    *,
    legacy_codex_bypass: bool | None = None,
    legacy_cursor_force: bool | None = None,
    legacy_cursor_approve_mcps: bool | None = None,
    legacy_cursor_sandbox_mode: str | None = None,
) -> AccessPolicy:
    if explicit_policy is not None and explicit_policy.strip():
        return normalize_access_policy(explicit_policy)

    if provider == "codex":
        if legacy_codex_bypass is True:
            return "owner"
        if legacy_codex_bypass is False:
            return "workspace-write"
        return "readonly"

    if provider == "cursor":
        sandbox_mode = (legacy_cursor_sandbox_mode or "").strip().lower()
        if sandbox_mode == "disabled":
            return "owner"
        if legacy_cursor_force or legacy_cursor_approve_mcps:
            return "owner"
        if sandbox_mode == "enabled":
            return "workspace-write"
        return "readonly"

    return "readonly"


def provider_display_name(provider: TextStreamProvider) -> str:
    if provider == "claude":
        return "Claude Code"
    if provider == "codex":
        return "Codex CLI"
    return "Cursor Agent"


def extract_text_from_content(content: list[dict[str, Any]]) -> str:
    text_parts: list[str] = []

    for block in content:
        if block.get("type") != "text":
            continue

        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    return " ".join(text_parts).strip()


def _humanize_identifier(value: str | None, fallback: str = "Artifact") -> str:
    if not value:
        return fallback

    normalized = re.sub(r"[_-]+", " ", value).strip()
    if not normalized:
        return fallback

    return normalized.title()


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip().lower()
    return normalized or None


def _command_to_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    if (
        isinstance(value, list)
        and value
        and all(isinstance(item, str) for item in value)
    ):
        return shlex.join(value)

    return None


def _json_to_string(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    if isinstance(value, (dict, list, int, float, bool)):
        return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)

    return None


def _render_tool_payload(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        for key in ("command", "cmd"):
            command = _command_to_string(value.get(key))
            if command:
                return command, "bash"

        for key in (
            "patch",
            "diff",
            "input",
            "arguments",
            "args",
            "params",
            "payload",
            "call",
        ):
            if key not in value:
                continue
            rendered, language = _render_tool_payload(value.get(key))
            if rendered:
                return rendered, language

        rendered = _json_to_string(value)
        if rendered:
            return rendered, "json"
        return None, None

    command = _command_to_string(value)
    if command:
        return command, "bash"

    rendered = _json_to_string(value)
    if isinstance(value, (list, dict)) and rendered:
        return rendered, "json"

    return rendered, None


def _build_artifact_title(
    *,
    kind: ArtifactKind,
    index: int,
    language: str | None = None,
    title_prefix: str | None = None,
) -> str:
    if title_prefix:
        base = title_prefix
    elif kind == "diff":
        base = "Diff"
    elif language:
        base = f"{_humanize_identifier(language, fallback='Code')} Snippet"
    else:
        base = "Code Snippet"

    return f"{base} {index}" if index > 1 else base


def _extract_embedded_code_artifacts(
    text: str,
    *,
    title_prefix: str | None = None,
    artifact_id_prefix: str | None = None,
) -> list[UiArtifact]:
    if not text:
        return []

    artifacts: list[UiArtifact] = []
    seen_bodies: set[str] = set()

    for index, match in enumerate(FENCED_CODE_BLOCK_RE.finditer(text), start=1):
        body = match.group("body").strip("\n")
        if not body or body in seen_bodies:
            continue

        seen_bodies.add(body)
        language = _normalize_language(match.group("lang"))
        kind: ArtifactKind = "diff" if language in {"diff", "patch"} else "code"
        artifact_id = (
            f"{artifact_id_prefix}:fence:{index}"
            if artifact_id_prefix
            else f"fence:{index}"
        )
        artifacts.append(
            UiArtifact(
                kind=kind,
                title=_build_artifact_title(
                    kind=kind,
                    index=index,
                    language=language,
                    title_prefix=title_prefix,
                ),
                text=body,
                language="diff" if kind == "diff" else language,
                artifact_id=artifact_id,
            )
        )

    patch_offset = len(artifacts)
    for index, match in enumerate(PATCH_BLOCK_RE.finditer(text), start=1):
        body = match.group(1).strip()
        if not body or body in seen_bodies:
            continue

        seen_bodies.add(body)
        artifact_id = (
            f"{artifact_id_prefix}:patch:{index}"
            if artifact_id_prefix
            else f"patch:{index}"
        )
        artifacts.append(
            UiArtifact(
                kind="diff",
                title=_build_artifact_title(
                    kind="diff",
                    index=patch_offset + index,
                    title_prefix=title_prefix,
                ),
                text=body,
                language="diff",
                artifact_id=artifact_id,
            )
        )

    return artifacts


def _looks_like_tool_block(block: dict[str, Any]) -> bool:
    block_type = _string_value(block.get("type")) or ""
    if block_type in {
        "tool_use",
        "tool_call",
        "tool-call",
        "function_call",
        "mcp_tool_call",
    }:
        return True

    if block_type in {"text", "thinking", "tool_result"}:
        return False

    return any(
        key in block
        for key in ("command", "cmd", "input", "arguments", "args", "params")
    )


def _extract_content_artifacts(
    *,
    provider: TextStreamProvider,
    content: list[dict[str, Any]],
    seen_artifact_ids: set[str],
) -> list[UiArtifact]:
    artifacts: list[UiArtifact] = []

    for index, block in enumerate(content, start=1):
        if not _looks_like_tool_block(block):
            continue

        block_type = _string_value(block.get("type")) or "tool"
        artifact_id = (
            _string_value(block.get("id")) or f"{provider}:{block_type}:{index}"
        )
        if artifact_id in seen_artifact_ids:
            continue

        seen_artifact_ids.add(artifact_id)
        title = _string_value(block.get("name")) or _humanize_identifier(
            block_type, fallback="Tool"
        )
        payload_value = None
        for key in (
            "input",
            "arguments",
            "args",
            "params",
            "payload",
            "call",
            "command",
            "cmd",
        ):
            if key in block:
                payload_value = block.get(key)
                break

        payload_text, language = _render_tool_payload(payload_value)
        tool_text = payload_text or title
        artifacts.append(
            UiArtifact(
                kind="tool",
                title=title,
                text=tool_text,
                language=language,
                artifact_id=artifact_id,
            )
        )
        artifacts.extend(
            _extract_embedded_code_artifacts(
                tool_text,
                title_prefix=title,
                artifact_id_prefix=artifact_id,
            )
        )

    return artifacts


def _extract_codex_item_artifacts(item: dict[str, Any]) -> list[UiArtifact]:
    item_type = _string_value(item.get("type"))
    if item_type in {None, "agent_message", "error"}:
        return []

    artifact_id = _string_value(item.get("id")) or item_type
    title = _string_value(item.get("name")) or _humanize_identifier(
        item_type, fallback="Tool"
    )
    payload_value = None
    for key in (
        "command",
        "cmd",
        "input",
        "arguments",
        "args",
        "params",
        "payload",
        "call",
        "patch",
        "diff",
    ):
        if key in item:
            payload_value = item.get(key)
            break

    if payload_value is None:
        payload_value = item

    payload_text, language = _render_tool_payload(payload_value)
    tool_text = payload_text or title
    artifacts = [
        UiArtifact(
            kind="tool",
            title=title,
            text=tool_text,
            language=language,
            artifact_id=artifact_id,
        )
    ]
    artifacts.extend(
        _extract_embedded_code_artifacts(
            tool_text,
            title_prefix=title,
            artifact_id_prefix=artifact_id,
        )
    )
    return artifacts


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _extract_text_candidate(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value

    if isinstance(value, dict):
        for key in ("delta", "text", "chunk"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text

        content = value.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                text = item.get("text")
                if (
                    item_type in {"output_text", "text"}
                    and isinstance(text, str)
                    and text
                ):
                    parts.append(text)
            if parts:
                return "".join(parts)

        for nested_key in ("payload", "item", "params", "content_item"):
            nested = _extract_text_candidate(value.get(nested_key))
            if nested:
                return nested

    return None


def _extract_codex_delta_text(event: dict[str, Any]) -> str | None:
    event_type = _string_value(event.get("type"))
    if event_type in {
        "agent_message_delta",
        "agent_message_content_delta",
        "item.delta",
        "item.updated",
    }:
        direct = _extract_text_candidate(event)
        if direct:
            return direct

        item = event.get("item")
        if isinstance(item, dict):
            item_type = _string_value(item.get("type"))
            if item_type in {"agent_message_delta", "agent_message_content_delta"}:
                return _extract_text_candidate(item)

    return None


def _embed_prompt_instructions(
    prompt: str,
    *,
    system_prompt: str | None = None,
    thinking_level: str | None = None,
) -> str:
    sections: list[str] = []
    if system_prompt:
        sections.append(system_prompt)
    if thinking_level:
        sections.append(
            "Reasoning guidance: "
            f"use {thinking_level} thinking effort before responding. "
            "Think carefully, then keep the spoken answer concise."
        )
    if not sections:
        return prompt
    sections.append(f"User request:\n{prompt}")
    return "\n\n".join(sections)


def _normalize_whitespace_with_end_indexes(text: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    raw_end_indexes: list[int] = []
    saw_non_whitespace = False
    pending_space = False

    for index, char in enumerate(text):
        if char.isspace():
            if saw_non_whitespace:
                pending_space = True
            continue

        if pending_space and normalized_chars:
            normalized_chars.append(" ")
            raw_end_indexes.append(index)
            pending_space = False

        normalized_chars.append(char)
        raw_end_indexes.append(index + 1)
        saw_non_whitespace = True

    return "".join(normalized_chars), raw_end_indexes


def _extract_incremental_text(text: str | None, emitted_text: str) -> str | None:
    if not text:
        return None
    if not emitted_text:
        return text
    if text == emitted_text:
        return None
    if text.startswith(emitted_text):
        suffix = text[len(emitted_text) :]
        return suffix or None

    normalized_text, raw_end_indexes = _normalize_whitespace_with_end_indexes(text)
    normalized_emitted, _ = _normalize_whitespace_with_end_indexes(emitted_text)
    if not normalized_text:
        return None
    if normalized_text == normalized_emitted:
        return None
    if (
        normalized_emitted
        and normalized_text.startswith(normalized_emitted)
        and raw_end_indexes
    ):
        raw_end_index = raw_end_indexes[len(normalized_emitted) - 1]
        suffix = text[raw_end_index:].lstrip()
        return suffix or None

    return text


def iter_final_text_artifacts(
    assistant_text: str,
    *,
    artifact_id_prefix: str,
) -> list[UiArtifact]:
    return _extract_embedded_code_artifacts(
        assistant_text,
        artifact_id_prefix=artifact_id_prefix,
    )
