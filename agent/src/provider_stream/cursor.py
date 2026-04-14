from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from .common import (
    DEFAULT_CURSOR_MODEL,
    SentenceChunker,
    TextStreamConfig,
    TextStreamEvent,
    _embed_prompt_instructions,
    _extract_content_artifacts,
    _extract_incremental_text,
    _extract_text_candidate,
    _string_value,
    extract_text_from_content,
    iter_final_text_artifacts,
    provider_display_name,
)
from .cursor_app import CursorAppTransport, build_cursor_app_submit_command
from .runner import ProcessRunner, terminate_process

READONLY_MODE_HINT = (
    "Runtime note: this RepoLine session is running in readonly mode. "
    "You may inspect and explain, but do not make file changes. "
    "If the user asks for edits, say briefly that this session is readonly."
)


class CursorProviderStreamAdapter:
    provider = "cursor"

    def __init__(
        self,
        *,
        app_transport: CursorAppTransport | None = None,
    ) -> None:
        self._app_transport = app_transport or CursorAppTransport()

    def build_command(self, config: TextStreamConfig) -> list[str]:
        if config.provider_transport == "app":
            return build_cursor_app_submit_command(config)

        system_prompt = config.system_prompt
        if config.access_policy == "readonly":
            system_prompt = (
                f"{system_prompt}\n\n{READONLY_MODE_HINT}"
                if system_prompt
                else READONLY_MODE_HINT
            )

        prompt = _embed_prompt_instructions(
            config.prompt,
            system_prompt=system_prompt,
            thinking_level=config.thinking_level,
        )

        cmd = ["cursor-agent", "-p", "--output-format", "stream-json", "--trust"]
        cmd.append("--stream-partial-output")
        if config.resume_session_id:
            cmd.extend(["--resume", config.resume_session_id])
        if config.access_policy in {"workspace-write", "owner"}:
            cmd.append("-f")
        if config.access_policy == "owner":
            cmd.extend(["--sandbox", "disabled"])
            cmd.append("--approve-mcps")
        else:
            cmd.extend(["--sandbox", "enabled"])
        model = config.model or DEFAULT_CURSOR_MODEL
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        return cmd

    async def stream(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]:
        if config.provider_transport == "app":
            async for event in self._app_transport.stream(config):
                yield event
            return

        chunker = SentenceChunker(config.chunk_chars)
        cmd = self.build_command(config)
        current_session_id = config.resume_session_id
        assistant_text = ""
        reported_error = False
        provider_name = provider_display_name("cursor")
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
                        text = extract_text_from_content(
                            content, preserve_whitespace=True
                        )
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

            for artifact in iter_final_text_artifacts(
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
            await terminate_process(proc)
            raise
        finally:
            if proc.returncode is None:
                await terminate_process(proc)
