from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from collections.abc import AsyncIterator
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
class TextStreamEvent:
    type: Literal["status", "speech_chunk", "artifact", "error", "done"]
    message: str | None = None
    text: str | None = None
    final: bool = False
    exit_code: int | None = None
    session_id: str | None = None
    artifact: UiArtifact | None = None


@dataclass(frozen=True, slots=True)
class UiArtifact:
    kind: ArtifactKind
    title: str
    text: str
    language: str | None = None
    artifact_id: str | None = None


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


def build_claude_command(config: TextStreamConfig) -> list[str]:
    if not config.session_id:
        raise ValueError("Claude provider requires a session_id")

    cmd = [
        "claude",
        "-p",
        "--verbose",
        "--output-format=stream-json",
        "--include-partial-messages",
    ]
    if config.access_policy == "readonly":
        cmd.extend(["--permission-mode", "plan"])
    elif config.access_policy == "workspace-write":
        cmd.extend(["--permission-mode", "acceptEdits"])
        cmd.extend(["--allowedTools", "Bash,Edit,MultiEdit,Write"])
        cmd.extend(["--disallowedTools", "WebFetch,WebSearch"])
    else:
        cmd.append("--dangerously-skip-permissions")
    if config.resume_session_id:
        cmd.extend(["--resume", config.resume_session_id, "--fork-session"])
    cmd.extend(["--session-id", config.session_id])
    if config.model:
        cmd.extend(["--model", config.model])
    if config.thinking_level:
        cmd.extend(["--effort", config.thinking_level])
    if config.system_prompt:
        cmd.extend(["--append-system-prompt", config.system_prompt])
    cmd.append(config.prompt)
    return cmd


def build_codex_command(config: TextStreamConfig) -> list[str]:
    prompt = _embed_prompt_instructions(
        config.prompt,
        system_prompt=config.system_prompt,
    )

    if config.resume_session_id:
        cmd = ["codex", "exec", "resume", "--json", "--skip-git-repo-check"]
    else:
        cmd = ["codex", "exec", "--json", "--color", "never", "--skip-git-repo-check"]

    if config.access_policy == "owner":
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    elif config.access_policy == "workspace-write":
        cmd.append("--full-auto")
    else:
        cmd.extend(["--sandbox", "read-only"])
    if config.thinking_level:
        cmd.extend(["-c", f'model_reasoning_effort="{config.thinking_level}"'])
    if config.model:
        cmd.extend(["--model", config.model])
    if config.resume_session_id:
        cmd.append(config.resume_session_id)
    cmd.append(prompt)
    return cmd


def build_cursor_command(config: TextStreamConfig) -> list[str]:
    prompt = _embed_prompt_instructions(
        config.prompt,
        system_prompt=config.system_prompt,
        thinking_level=config.thinking_level,
    )

    cmd = ["cursor-agent", "-p", "--output-format", "stream-json"]
    if config.access_policy == "readonly":
        cmd.extend(["--mode", "plan"])
    if config.resume_session_id:
        cmd.extend(["--resume", config.resume_session_id])
    if config.access_policy in {"workspace-write", "owner"}:
        cmd.append("-f")
    if config.access_policy == "owner":
        cmd.extend(["--sandbox", "disabled"])
        cmd.append("--approve-mcps")
    else:
        cmd.extend(["--sandbox", "enabled"])
    if config.model:
        cmd.extend(["--model", config.model])
    cmd.append(prompt)
    return cmd


def build_stream_command(config: TextStreamConfig) -> list[str]:
    provider = normalize_provider(config.provider)
    if provider == "claude":
        return build_claude_command(config)
    if provider == "codex":
        return build_codex_command(config)
    return build_cursor_command(config)


async def stream_text_events(
    config: TextStreamConfig,
) -> AsyncIterator[TextStreamEvent]:
    provider = normalize_provider(config.provider)
    if provider == "claude":
        async for event in _stream_claude_events(config):
            yield event
        return

    if provider == "codex":
        async for event in _stream_codex_events(config):
            yield event
        return

    async for event in _stream_cursor_events(config):
        yield event


async def stream_text_chunks(
    config: TextStreamConfig,
) -> AsyncIterator[str]:
    saw_text = False
    error_message: str | None = None

    async for event in stream_text_events(config):
        if event.type == "speech_chunk" and event.text:
            saw_text = True
            yield event.text
            continue

        if event.type == "error":
            error_message = (
                event.message or f"{provider_display_name(config.provider)} failed."
            )
            break

    if error_message:
        if saw_text:
            return
        raise TextStreamError(error_message)

    if not saw_text:
        raise TextStreamError(
            f"{provider_display_name(config.provider)} finished without producing speech text."
        )


def _iter_final_text_artifacts(
    assistant_text: str,
    *,
    artifact_id_prefix: str,
) -> list[UiArtifact]:
    return _extract_embedded_code_artifacts(
        assistant_text,
        artifact_id_prefix=artifact_id_prefix,
    )


async def _stream_claude_events(
    config: TextStreamConfig,
) -> AsyncIterator[TextStreamEvent]:
    chunker = SentenceChunker(config.chunk_chars)
    cmd = build_claude_command(config)
    assistant_text = ""
    reported_error = False
    provider_name = provider_display_name("claude")
    seen_artifact_ids: set[str] = set()

    proc = await _spawn_process(cmd, config.working_directory)

    try:
        yield TextStreamEvent(
            type="status", message=f"Starting {provider_name} stream."
        )

        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            if event_type == "assistant":
                message = event.get("message", {})
                content = message.get("content", [])
                if isinstance(content, list):
                    for artifact in _extract_content_artifacts(
                        provider="claude",
                        content=content,
                        seen_artifact_ids=seen_artifact_ids,
                    ):
                        yield TextStreamEvent(
                            type="artifact",
                            artifact=artifact,
                            session_id=config.session_id,
                        )
                    assistant_text = extract_text_from_content(content)
                continue

            if event_type == "result":
                if event.get("is_error"):
                    reported_error = True
                    yield TextStreamEvent(
                        type="error",
                        message=(
                            event.get("result")
                            or assistant_text
                            or f"{provider_name} failed."
                        ),
                        exit_code=proc.returncode,
                        session_id=config.session_id,
                    )
                    break

                for chunk in chunker.flush():
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                        session_id=config.session_id,
                    )
                break

            if event_type != "stream_event":
                continue

            inner = event.get("event", {})
            inner_type = inner.get("type")

            if inner_type == "message_start":
                yield TextStreamEvent(
                    type="status",
                    message=f"{provider_name} accepted the turn.",
                    session_id=config.session_id,
                )
                continue

            if inner_type == "message_stop":
                for chunk in chunker.flush():
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                        session_id=config.session_id,
                    )
                continue

            if inner_type != "content_block_delta":
                continue

            text = inner.get("delta", {}).get("text")
            if not text:
                continue

            for chunk in chunker.feed(text):
                yield TextStreamEvent(
                    type="speech_chunk",
                    text=chunk,
                    final=False,
                    session_id=config.session_id,
                )

        return_code = await proc.wait()
        if return_code != 0 and not reported_error:
            yield TextStreamEvent(
                type="error",
                message=assistant_text
                or f"{provider_name} exited with code {return_code}.",
                exit_code=return_code,
                session_id=config.session_id,
            )
            return

        for artifact in _iter_final_text_artifacts(
            assistant_text,
            artifact_id_prefix=f"claude:{config.session_id or 'session'}:assistant",
        ):
            yield TextStreamEvent(
                type="artifact", artifact=artifact, session_id=config.session_id
            )

        yield TextStreamEvent(
            type="done", exit_code=return_code, session_id=config.session_id
        )
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    finally:
        if proc.returncode is None:
            await _terminate_process(proc)


async def _stream_codex_events(
    config: TextStreamConfig,
) -> AsyncIterator[TextStreamEvent]:
    chunker = SentenceChunker(config.chunk_chars)
    cmd = build_codex_command(config)
    current_session_id = config.resume_session_id
    assistant_text = ""
    reported_error = False
    provider_name = provider_display_name("codex")

    proc = await _spawn_process(cmd, config.working_directory)

    try:
        yield TextStreamEvent(
            type="status",
            message=f"Starting {provider_name} stream.",
            session_id=current_session_id,
        )

        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")

            if event_type == "thread.started":
                current_session_id = (
                    _string_value(event.get("thread_id")) or current_session_id
                )
                yield TextStreamEvent(
                    type="status",
                    message=f"{provider_name} started a session.",
                    session_id=current_session_id,
                )
                continue

            if event_type in {"turn.started", "task_started"}:
                yield TextStreamEvent(
                    type="status",
                    message=f"{provider_name} accepted the turn.",
                    session_id=current_session_id,
                )
                continue

            delta_text = _extract_codex_delta_text(event)
            if delta_text:
                assistant_text += delta_text
                for chunk in chunker.feed(delta_text):
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=False,
                        session_id=current_session_id,
                    )
                continue

            if event_type == "item.completed":
                item = event.get("item", {})
                item_type = item.get("type")

                if item_type == "error":
                    message = _string_value(item.get("message"))
                    if message and message.startswith(
                        "Under-development features enabled:"
                    ):
                        yield TextStreamEvent(
                            type="status",
                            message=message,
                            session_id=current_session_id,
                        )
                        continue

                    reported_error = True
                    yield TextStreamEvent(
                        type="error",
                        message=message or assistant_text or f"{provider_name} failed.",
                        exit_code=proc.returncode,
                        session_id=current_session_id,
                    )
                    break

                if item_type == "agent_message":
                    text = _extract_text_candidate(item)
                    if text:
                        assistant_text += text
                        for chunk in chunker.feed(text):
                            yield TextStreamEvent(
                                type="speech_chunk",
                                text=chunk,
                                final=False,
                                session_id=current_session_id,
                            )
                    continue

                for artifact in _extract_codex_item_artifacts(item):
                    yield TextStreamEvent(
                        type="artifact",
                        artifact=artifact,
                        session_id=current_session_id,
                    )
                continue

            if event_type in {"turn.completed", "task_complete"}:
                if not assistant_text:
                    assistant_text = (
                        _string_value(event.get("last_agent_message")) or assistant_text
                    )
                    if assistant_text:
                        for chunk in chunker.feed(assistant_text):
                            yield TextStreamEvent(
                                type="speech_chunk",
                                text=chunk,
                                final=False,
                                session_id=current_session_id,
                            )

                for chunk in chunker.flush():
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                        session_id=current_session_id,
                    )
                continue

        return_code = await proc.wait()
        if return_code != 0 and not reported_error:
            yield TextStreamEvent(
                type="error",
                message=assistant_text
                or f"{provider_name} exited with code {return_code}.",
                exit_code=return_code,
                session_id=current_session_id,
            )
            return

        for artifact in _iter_final_text_artifacts(
            assistant_text,
            artifact_id_prefix=f"codex:{current_session_id or 'session'}:assistant",
        ):
            yield TextStreamEvent(
                type="artifact",
                artifact=artifact,
                session_id=current_session_id,
            )

        yield TextStreamEvent(
            type="done", exit_code=return_code, session_id=current_session_id
        )
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    finally:
        if proc.returncode is None:
            await _terminate_process(proc)


async def _stream_cursor_events(
    config: TextStreamConfig,
) -> AsyncIterator[TextStreamEvent]:
    chunker = SentenceChunker(config.chunk_chars)
    cmd = build_cursor_command(config)
    current_session_id = config.resume_session_id
    assistant_text = ""
    reported_error = False
    provider_name = provider_display_name("cursor")
    seen_artifact_ids: set[str] = set()

    proc = await _spawn_process(cmd, config.working_directory)

    try:
        yield TextStreamEvent(
            type="status",
            message=f"Starting {provider_name} stream.",
            session_id=current_session_id,
        )

        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = _string_value(event.get("session_id"))
            if session_id:
                current_session_id = session_id

            event_type = _string_value(event.get("type"))
            if event_type == "system" and _string_value(event.get("subtype")) == "init":
                yield TextStreamEvent(
                    type="status",
                    message=f"{provider_name} started a session.",
                    session_id=current_session_id,
                )
                continue

            if event_type == "assistant":
                message = event.get("message", {})
                content = message.get("content", [])
                if isinstance(content, list):
                    for artifact in _extract_content_artifacts(
                        provider="cursor",
                        content=content,
                        seen_artifact_ids=seen_artifact_ids,
                    ):
                        yield TextStreamEvent(
                            type="artifact",
                            artifact=artifact,
                            session_id=current_session_id,
                        )
                    text = extract_text_from_content(content)
                else:
                    text = _extract_text_candidate(message) or ""
                delta_text = _extract_incremental_text(text, assistant_text)
                if not delta_text:
                    continue

                assistant_text += delta_text
                for chunk in chunker.feed(delta_text):
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=False,
                        session_id=current_session_id,
                    )
                continue

            if event_type == "result":
                if event.get("is_error"):
                    reported_error = True
                    yield TextStreamEvent(
                        type="error",
                        message=(
                            _string_value(event.get("result"))
                            or assistant_text
                            or f"{provider_name} failed."
                        ),
                        exit_code=proc.returncode,
                        session_id=current_session_id,
                    )
                    break

                result_text = _string_value(event.get("result"))
                delta_text = _extract_incremental_text(result_text, assistant_text)
                if delta_text:
                    assistant_text += delta_text
                    for chunk in chunker.feed(delta_text):
                        yield TextStreamEvent(
                            type="speech_chunk",
                            text=chunk,
                            final=False,
                            session_id=current_session_id,
                        )

                for chunk in chunker.flush():
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                        session_id=current_session_id,
                    )
                continue

        return_code = await proc.wait()
        if return_code != 0 and not reported_error:
            yield TextStreamEvent(
                type="error",
                message=assistant_text
                or f"{provider_name} exited with code {return_code}.",
                exit_code=return_code,
                session_id=current_session_id,
            )
            return

        for artifact in _iter_final_text_artifacts(
            assistant_text,
            artifact_id_prefix=f"cursor:{current_session_id or 'session'}:assistant",
        ):
            yield TextStreamEvent(
                type="artifact",
                artifact=artifact,
                session_id=current_session_id,
            )

        yield TextStreamEvent(
            type="done", exit_code=return_code, session_id=current_session_id
        )
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    finally:
        if proc.returncode is None:
            await _terminate_process(proc)


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


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


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
    return text


async def _spawn_process(
    cmd: list[str],
    working_directory: str | None,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=working_directory or None,
        env=os.environ.copy(),
    )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2)
        return
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
