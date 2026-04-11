from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from typing import AsyncIterator, Literal


SENTENCE_END_RE = re.compile(r"(.+?[.!?](?:['\"])?(?:\s+|$))", re.DOTALL)


class ClaudeStreamError(RuntimeError):
    """Raised when Claude Code exits before producing a usable response."""


@dataclass(frozen=True, slots=True)
class ClaudeStreamConfig:
    prompt: str
    session_id: str
    resume_session_id: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    working_directory: str | None = None
    chunk_chars: int = 140


@dataclass(frozen=True, slots=True)
class ClaudeStreamEvent:
    type: Literal["status", "speech_chunk", "error", "done"]
    message: str | None = None
    text: str | None = None
    final: bool = False
    exit_code: int | None = None


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


def extract_text_from_content(content: list[dict[str, Any]]) -> str:
    text_parts: list[str] = []

    for block in content:
        if block.get("type") != "text":
            continue

        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    return " ".join(text_parts).strip()


def build_claude_command(config: ClaudeStreamConfig) -> list[str]:
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


async def stream_claude_events(
    config: ClaudeStreamConfig,
) -> AsyncIterator[ClaudeStreamEvent]:
    chunker = SentenceChunker(config.chunk_chars)
    cmd = build_claude_command(config)
    assistant_text = ""
    reported_error = False

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=config.working_directory or None,
        env=os.environ.copy(),
    )

    try:
        yield ClaudeStreamEvent(type="status", message="Starting Claude Code stream.")

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
                    yield ClaudeStreamEvent(
                        type="error",
                        message=(event.get("result") or assistant_text or "Claude Code failed."),
                        exit_code=proc.returncode,
                    )
                    break

                for chunk in chunker.flush():
                    yield ClaudeStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                    )
                break

            if event_type != "stream_event":
                continue

            inner = event.get("event", {})
            inner_type = inner.get("type")

            if inner_type == "message_start":
                yield ClaudeStreamEvent(
                    type="status",
                    message="Claude Code accepted the turn.",
                )
                continue

            if inner_type == "message_stop":
                for chunk in chunker.flush():
                    yield ClaudeStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                    )
                continue

            if inner_type != "content_block_delta":
                continue

            text = inner.get("delta", {}).get("text")
            if not text:
                continue

            for chunk in chunker.feed(text):
                yield ClaudeStreamEvent(
                    type="speech_chunk",
                    text=chunk,
                    final=False,
                )

        return_code = await proc.wait()
        if return_code != 0 and not reported_error:
            yield ClaudeStreamEvent(
                type="error",
                message=assistant_text or f"Claude Code exited with code {return_code}.",
                exit_code=return_code,
            )
            return

        yield ClaudeStreamEvent(type="done", exit_code=return_code)
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    finally:
        if proc.returncode is None:
            await _terminate_process(proc)


async def stream_claude_chunks(
    config: ClaudeStreamConfig,
) -> AsyncIterator[str]:
    saw_text = False
    error_message: str | None = None

    async for event in stream_claude_events(config):
        if event.type == "speech_chunk" and event.text:
            saw_text = True
            yield event.text
            continue

        if event.type == "error":
            error_message = event.message or "Claude Code failed."
            break

    if error_message:
        if saw_text:
            return
        raise ClaudeStreamError(error_message)

    if not saw_text:
        raise ClaudeStreamError("Claude Code finished without producing speech text.")


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
