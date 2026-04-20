from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from .common import (
    DEFAULT_GEMINI_MODEL,
    SentenceChunker,
    TextStreamConfig,
    TextStreamEvent,
    _embed_prompt_instructions,
    _extract_error_message,
    _extract_content_artifacts,
    _extract_incremental_text,
    _extract_text_candidate,
    _string_value,
    iter_final_text_artifacts,
    provider_display_name,
)
from .runner import ProcessRunner, terminate_process


class GeminiProviderStreamAdapter:
    provider = "gemini"

    def build_command(self, config: TextStreamConfig) -> list[str]:
        if config.provider_transport not in {None, "cli"}:
            raise ValueError(
                "Gemini only supports the Gemini CLI transport after the hard cutover."
            )

        model = config.model or DEFAULT_GEMINI_MODEL
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
                    yield TextStreamEvent(
                        type="assistant_delta",
                        text=delta_text,
                        session_id=current_session_id,
                    )
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
                        error_message = (
                            _extract_error_message(event.get("error"))
                            or _extract_error_message(event.get("result"))
                            or assistant_text
                            or f"{provider_name} failed with status {status}."
                        )
                        reported_error = True
                        yield TextStreamEvent(
                            type="error",
                            message=error_message,
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
