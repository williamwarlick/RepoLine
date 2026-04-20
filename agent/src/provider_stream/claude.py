from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from .common import (
    SentenceChunker,
    TextStreamConfig,
    TextStreamEvent,
    _extract_content_artifacts,
    extract_text_from_content,
    iter_final_text_artifacts,
    provider_display_name,
)
from .runner import ProcessRunner, terminate_process


class ClaudeProviderStreamAdapter:
    provider = "claude"

    def build_command(self, config: TextStreamConfig) -> list[str]:
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

    async def stream(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]:
        chunker = SentenceChunker(config.chunk_chars)
        cmd = self.build_command(config)
        assistant_text = ""
        reported_error = False
        provider_name = provider_display_name("claude")
        seen_artifact_ids: set[str] = set()

        proc = await runner.spawn_jsonl(cmd, config.working_directory)

        try:
            yield TextStreamEvent(
                type="status", message=f"Starting {provider_name} stream."
            )

            async for line in proc.iter_lines():
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

                yield TextStreamEvent(
                    type="assistant_delta",
                    text=text,
                    session_id=config.session_id,
                )
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

            for artifact in iter_final_text_artifacts(
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
            await terminate_process(proc)
            raise
        finally:
            if proc.returncode is None:
                await terminate_process(proc)
