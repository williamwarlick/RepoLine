from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from .common import (
    SentenceChunker,
    TextStreamConfig,
    TextStreamEvent,
    _embed_prompt_instructions,
    _extract_codex_delta_text,
    _extract_codex_item_artifacts,
    _extract_incremental_text,
    _extract_text_candidate,
    _string_value,
    iter_final_text_artifacts,
    provider_display_name,
)
from .runner import ProcessRunner, terminate_process


class CodexProviderStreamAdapter:
    provider = "codex"

    def build_command(self, config: TextStreamConfig) -> list[str]:
        prompt = _embed_prompt_instructions(
            config.prompt,
            system_prompt=config.system_prompt,
        )

        if config.resume_session_id:
            cmd = ["codex", "exec", "resume", "--json", "--skip-git-repo-check"]
        else:
            cmd = [
                "codex",
                "exec",
                "--json",
                "--color",
                "never",
                "--skip-git-repo-check",
            ]

        if config.access_policy == "owner":
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        elif config.access_policy == "workspace-write":
            cmd.append("--full-auto")
        else:
            if config.resume_session_id:
                cmd.extend(
                    [
                        "-c",
                        'sandbox_mode="read-only"',
                    ]
                )
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

    async def stream(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]:
        chunker = SentenceChunker(config.chunk_chars)
        cmd = self.build_command(config)
        current_session_id = config.resume_session_id
        assistant_text = ""
        reported_error = False
        provider_name = provider_display_name("codex")

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
                            message=message
                            or assistant_text
                            or f"{provider_name} failed.",
                            exit_code=proc.returncode,
                            session_id=current_session_id,
                        )
                        break

                    if item_type == "agent_message":
                        text = _extract_text_candidate(item)
                        delta_text = _extract_incremental_text(text, assistant_text)
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
                            _string_value(event.get("last_agent_message"))
                            or assistant_text
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

            for artifact in iter_final_text_artifacts(
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
            await terminate_process(proc)
            raise
        finally:
            if proc.returncode is None:
                await terminate_process(proc)
