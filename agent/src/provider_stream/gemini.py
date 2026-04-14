from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from .common import (
    DEFAULT_GEMINI_MODEL,
    SentenceChunker,
    TextStreamConfig,
    TextStreamError,
    TextStreamEvent,
    _embed_prompt_instructions,
    _extract_content_artifacts,
    _extract_incremental_text,
    _extract_text_candidate,
    _string_value,
    iter_final_text_artifacts,
    provider_display_name,
)
from .runner import ProcessRunner, terminate_process

_GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiApiTransport(Protocol):
    async def stream_generate_content(
        self,
        *,
        api_key: str,
        model: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]: ...


class HttpxGeminiApiTransport:
    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    async def stream_generate_content(
        self,
        *,
        api_key: str,
        model: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        url = f"{_GEMINI_API_BASE_URL}/models/{model}:streamGenerateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        params = {"alt": "sse"}

        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                "POST", url, headers=headers, params=params, json=payload
            ) as response,
        ):
            if response.status_code >= 400:
                body = await response.aread()
                raise TextStreamError(
                    _format_gemini_api_error(
                        response.status_code,
                        body.decode("utf-8", errors="replace"),
                    )
                )

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                payload_json = line[6:].strip()
                if not payload_json:
                    continue

                try:
                    event = json.loads(payload_json)
                except json.JSONDecodeError:
                    continue

                if isinstance(event, dict):
                    yield event


class GeminiProviderStreamAdapter:
    provider = "gemini"

    def __init__(
        self,
        *,
        api_transport: GeminiApiTransport | None = None,
    ) -> None:
        self._api_transport = api_transport or HttpxGeminiApiTransport()
        self._session_history: dict[str, list[dict[str, Any]]] = {}
        self._history_lock = asyncio.Lock()

    def build_command(self, config: TextStreamConfig) -> list[str]:
        model = config.model or DEFAULT_GEMINI_MODEL
        transport = _resolve_transport(config)

        if transport == "api":
            cmd = ["gemini-api", "--model", model]
            if _should_disable_thinking_budget(config):
                cmd.extend(["--thinking-budget", "0"])
            return cmd

        prompt = _embed_prompt_instructions(
            config.prompt,
            system_prompt=config.system_prompt,
            thinking_level=config.thinking_level,
        )

        cmd = ["gemini", "--output-format", "stream-json", "-p", prompt]
        if config.access_policy == "readonly":
            cmd.extend(["--approval-mode", "plan", "--sandbox"])
        elif config.access_policy == "workspace-write":
            cmd.extend(["--approval-mode", "auto_edit", "--sandbox"])
        else:
            cmd.append("--yolo")
        if config.resume_session_id:
            cmd.extend(["--resume", config.resume_session_id])
        if model:
            cmd.extend(["--model", model])
        return cmd

    async def stream(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]:
        transport = _resolve_transport(config)
        if transport == "api":
            async for event in self._stream_api(config):
                yield event
            return

        async for event in self._stream_cli(config, runner):
            yield event

    async def _stream_cli(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]:
        chunker = SentenceChunker(config.chunk_chars)
        cmd = self.build_command(config)
        current_session_id = config.resume_session_id
        assistant_text = ""
        reported_error = False
        provider_name = provider_display_name("gemini")
        seen_artifact_ids: set[str] = set()

        proc = await runner.spawn_jsonl(cmd, config.working_directory)

        try:
            yield TextStreamEvent(
                type="status",
                message=f"Starting {provider_name} stream.",
                session_id=current_session_id,
            )

            async for line in proc.iter_lines():
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = _string_value(event.get("type"))
                session_id = _string_value(event.get("session_id"))
                if session_id:
                    current_session_id = session_id

                if event_type == "init":
                    yield TextStreamEvent(
                        type="status",
                        message=f"{provider_name} started a session.",
                        session_id=current_session_id,
                    )
                    continue

                if event_type == "tool_use":
                    parameters = event.get("parameters")
                    content = [
                        {
                            "type": "tool_use",
                            "id": _string_value(event.get("tool_id")) or "tool_use",
                            "name": _string_value(event.get("tool_name")) or "tool_use",
                            "input": parameters if isinstance(parameters, dict) else {},
                        }
                    ]
                    for artifact in _extract_content_artifacts(
                        provider="gemini",
                        content=content,
                        seen_artifact_ids=seen_artifact_ids,
                    ):
                        yield TextStreamEvent(
                            type="artifact",
                            artifact=artifact,
                            session_id=current_session_id,
                        )
                    continue

                if (
                    event_type == "message"
                    and _string_value(event.get("role")) == "assistant"
                ):
                    text = _extract_text_candidate(event.get("content"))
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
                    status = _string_value(event.get("status")) or "success"
                    if status != "success":
                        reported_error = True
                        yield TextStreamEvent(
                            type="error",
                            message=assistant_text
                            or f"{provider_name} failed with status {status}.",
                            exit_code=proc.returncode,
                            session_id=current_session_id,
                        )
                        break

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

            for artifact in iter_final_text_artifacts(
                assistant_text,
                artifact_id_prefix=f"gemini:{current_session_id or 'session'}:assistant",
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
            await terminate_process(proc)
            raise
        finally:
            if proc.returncode is None:
                await terminate_process(proc)

    async def _stream_api(self, config: TextStreamConfig) -> AsyncIterator[TextStreamEvent]:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            yield TextStreamEvent(
                type="error",
                message=(
                    "Gemini API transport requires GEMINI_API_KEY or GOOGLE_API_KEY."
                ),
            )
            return

        model = config.model or DEFAULT_GEMINI_MODEL
        provider_name = provider_display_name("gemini", "api")
        current_session_id = config.resume_session_id or str(uuid.uuid4())
        chunker = SentenceChunker(config.chunk_chars)
        assistant_text = ""

        async with self._history_lock:
            history = list(self._session_history.get(current_session_id, ()))

        payload = _build_gemini_api_payload(config, history)

        yield TextStreamEvent(
            type="status",
            message=f"Starting {provider_name} stream.",
            session_id=current_session_id,
        )

        try:
            yield TextStreamEvent(
                type="status",
                message=f"{provider_name} accepted the turn.",
                session_id=current_session_id,
            )
            async for event in self._api_transport.stream_generate_content(
                api_key=api_key,
                model=model,
                payload=payload,
            ):
                delta_text = _extract_incremental_text(
                    _extract_gemini_api_text(event), assistant_text
                )
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
        except asyncio.CancelledError:
            raise
        except TextStreamError as exc:
            yield TextStreamEvent(
                type="error",
                message=str(exc),
                session_id=current_session_id,
            )
            return
        except httpx.HTTPError as exc:
            yield TextStreamEvent(
                type="error",
                message=f"{provider_name} request failed: {exc}",
                session_id=current_session_id,
            )
            return

        if not assistant_text.strip():
            yield TextStreamEvent(
                type="error",
                message=f"{provider_name} finished without producing speech text.",
                session_id=current_session_id,
            )
            return

        for chunk in chunker.flush():
            yield TextStreamEvent(
                type="speech_chunk",
                text=chunk,
                final=True,
                session_id=current_session_id,
            )

        async with self._history_lock:
            updated_history = list(history)
            updated_history.append(_gemini_api_message("user", config.prompt))
            updated_history.append(_gemini_api_message("model", assistant_text))
            self._session_history[current_session_id] = updated_history

        for artifact in iter_final_text_artifacts(
            assistant_text,
            artifact_id_prefix=f"gemini-api:{current_session_id}:assistant",
        ):
            yield TextStreamEvent(
                type="artifact",
                artifact=artifact,
                session_id=current_session_id,
            )

        yield TextStreamEvent(type="done", exit_code=0, session_id=current_session_id)


def _resolve_transport(config: TextStreamConfig) -> str:
    transport = config.provider_transport or os.environ.get("BRIDGE_GEMINI_TRANSPORT")
    normalized = (transport or "cli").strip().lower()
    return "api" if normalized == "api" else "cli"


def _build_gemini_api_payload(
    config: TextStreamConfig, history: list[dict[str, Any]]
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contents": [*history, _gemini_api_message("user", config.prompt)],
    }

    system_instruction = _gemini_api_system_instruction(config)
    if system_instruction:
        payload["system_instruction"] = {
            "parts": [{"text": system_instruction}],
        }

    generation_config: dict[str, Any] = {}
    if _should_disable_thinking_budget(config):
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
    if generation_config:
        payload["generationConfig"] = generation_config

    return payload


def _gemini_api_system_instruction(config: TextStreamConfig) -> str | None:
    sections: list[str] = []
    if config.system_prompt:
        sections.append(config.system_prompt)
    if config.thinking_level:
        sections.append(
            "Reasoning guidance: "
            f"use {config.thinking_level} thinking effort before responding. "
            "Think carefully, then keep the spoken answer concise."
        )
    sections.append(
        "Runtime note: this fast Gemini API mode does not have local CLI tools or repo "
        "file access. If the user asks you to inspect files, run commands, or make "
        "changes, say that plainly instead of implying that you did it."
    )
    prompt = "\n\n".join(section for section in sections if section.strip())
    return prompt or None


def _should_disable_thinking_budget(config: TextStreamConfig) -> bool:
    model = (config.model or DEFAULT_GEMINI_MODEL).strip().lower()
    if not model.startswith("gemini-2.5"):
        return False
    if not config.thinking_level:
        return True
    return config.thinking_level.strip().lower() in {"none", "minimal", "low"}


def _gemini_api_message(role: str, text: str) -> dict[str, Any]:
    return {
        "role": role,
        "parts": [{"text": text}],
    }


def _extract_gemini_api_text(event: dict[str, Any]) -> str | None:
    text_parts: list[str] = []
    candidates = event.get("candidates")
    if not isinstance(candidates, list):
        return None

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = _string_value(part.get("text"))
            if text:
                text_parts.append(text)

    if not text_parts:
        return None
    return "".join(text_parts)


def _format_gemini_api_error(status_code: int, body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = _string_value(error.get("message"))
            if message:
                return f"Gemini API request failed ({status_code}): {message}"

    stripped = body.strip()
    if stripped:
        return f"Gemini API request failed ({status_code}): {stripped}"
    return f"Gemini API request failed with status {status_code}."
