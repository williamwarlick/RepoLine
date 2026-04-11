from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

TextStreamProvider = Literal["claude", "codex"]
SENTENCE_END_RE = re.compile(r"(.+?[.!?](?:['\"])?(?:\s+|$))", re.DOTALL)


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
    working_directory: str | None = None
    chunk_chars: int = 140
    codex_dangerously_bypass_approvals_and_sandbox: bool = True


@dataclass(frozen=True, slots=True)
class TextStreamEvent:
    type: Literal["status", "speech_chunk", "error", "done"]
    message: str | None = None
    text: str | None = None
    final: bool = False
    exit_code: int | None = None
    session_id: str | None = None


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
    if normalized not in {"claude", "codex"}:
        raise ValueError(f"unsupported bridge provider: {value}")
    return normalized  # type: ignore[return-value]


def provider_display_name(provider: TextStreamProvider) -> str:
    return "Claude Code" if provider == "claude" else "Codex CLI"


def extract_text_from_content(content: list[dict[str, Any]]) -> str:
    text_parts: list[str] = []

    for block in content:
        if block.get("type") != "text":
            continue

        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    return " ".join(text_parts).strip()


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
    if config.resume_session_id:
        cmd.extend(["--resume", config.resume_session_id, "--fork-session"])
    cmd.extend(["--session-id", config.session_id])
    if config.model:
        cmd.extend(["--model", config.model])
    if config.system_prompt:
        cmd.extend(["--append-system-prompt", config.system_prompt])
    cmd.append(config.prompt)
    return cmd


def build_codex_command(config: TextStreamConfig) -> list[str]:
    prompt = config.prompt
    if config.system_prompt:
        prompt = f"{config.system_prompt}\n\nUser request:\n{prompt}"

    if config.resume_session_id:
        cmd = ["codex", "exec", "resume", "--json", "--skip-git-repo-check"]
    else:
        cmd = ["codex", "exec", "--json", "--color", "never", "--skip-git-repo-check"]

    if config.codex_dangerously_bypass_approvals_and_sandbox:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        cmd.append("--full-auto")
    if config.model:
        cmd.extend(["--model", config.model])
    if config.resume_session_id:
        cmd.append(config.resume_session_id)
    cmd.append(prompt)
    return cmd


def build_stream_command(config: TextStreamConfig) -> list[str]:
    provider = normalize_provider(config.provider)
    if provider == "claude":
        return build_claude_command(config)
    return build_codex_command(config)


async def stream_text_events(
    config: TextStreamConfig,
) -> AsyncIterator[TextStreamEvent]:
    provider = normalize_provider(config.provider)
    if provider == "claude":
        async for event in _stream_claude_events(config):
            yield event
        return

    async for event in _stream_codex_events(config):
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
            error_message = event.message or f"{provider_display_name(config.provider)} failed."
            break

    if error_message:
        if saw_text:
            return
        raise TextStreamError(error_message)

    if not saw_text:
        raise TextStreamError(
            f"{provider_display_name(config.provider)} finished without producing speech text."
        )


async def _stream_claude_events(
    config: TextStreamConfig,
) -> AsyncIterator[TextStreamEvent]:
    chunker = SentenceChunker(config.chunk_chars)
    cmd = build_claude_command(config)
    assistant_text = ""
    reported_error = False
    provider_name = provider_display_name("claude")

    proc = await _spawn_process(cmd, config.working_directory)

    try:
        yield TextStreamEvent(type="status", message=f"Starting {provider_name} stream.")

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
                assistant_text = extract_text_from_content(message.get("content", []))
                continue

            if event_type == "result":
                if event.get("is_error"):
                    reported_error = True
                    yield TextStreamEvent(
                        type="error",
                        message=(event.get("result") or assistant_text or f"{provider_name} failed."),
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
                message=assistant_text or f"{provider_name} exited with code {return_code}.",
                exit_code=return_code,
                session_id=config.session_id,
            )
            return

        yield TextStreamEvent(type="done", exit_code=return_code, session_id=config.session_id)
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
                current_session_id = _string_value(event.get("thread_id")) or current_session_id
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
                    if message and message.startswith("Under-development features enabled:"):
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
                    text = _string_value(item.get("text"))
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

            if event_type in {"turn.completed", "task_complete"}:
                if not assistant_text:
                    assistant_text = _string_value(event.get("last_agent_message")) or assistant_text
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
                message=assistant_text or f"{provider_name} exited with code {return_code}.",
                exit_code=return_code,
                session_id=current_session_id,
            )
            return

        yield TextStreamEvent(type="done", exit_code=return_code, session_id=current_session_id)
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
                if item_type in {"output_text", "text"} and isinstance(text, str) and text:
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
