from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

from cursor_app_submit import (
    DEFAULT_CURSOR_APP_COMMAND_TITLE,
    CursorAppSubmitError,
    CursorAppSubmitResult,
    submit_prompt_to_cursor_app,
)
from cursor_app_tap import (
    CursorBubbleUpdate,
    CursorComposerTail,
    find_active_composer_id,
    load_bubbles,
    load_composer_data,
)

from .common import (
    SentenceChunker,
    TextStreamConfig,
    TextStreamError,
    TextStreamEvent,
    UiArtifact,
    iter_final_text_artifacts,
    provider_display_name,
)

APP_STREAM_POLL_INTERVAL_SECONDS = 0.02
APP_SETTLE_DELAY_SECONDS = 0.05
APP_RESPONSE_TIMEOUT_SECONDS = 20.0
REPOLINE_ROOT = Path(__file__).resolve().parents[3]
VOICE_MODE_HINT = (
    "Voice mode. Answer immediately. No markdown, bold labels, or headings. "
    "Keep it to one or two short sentences. Ask at most one short question. "
    "Do not inspect the repo unless the user needs repo-specific facts. "
    "For questions asking what this repo, project, or app is, answer directly first "
    "from obvious repo identity and only inspect files if the user asks for more detail. "
    "Prefer the obvious product or project name over the raw folder name when both are clear."
)


class CursorAppSubmitter(Protocol):
    async def submit(
        self,
        *,
        workspace_root: str | Path,
        prompt: str,
        command_title: str,
        submit_mode: str | None,
        start_new_composer: bool = False,
    ) -> CursorAppSubmitResult: ...


class CursorComposerTailProtocol(Protocol):
    def seed_known_bubbles(self, bubbles: list[Any]) -> None: ...

    def snapshot_updates(
        self, *, include_existing: bool = False
    ) -> list[CursorBubbleUpdate]: ...


class DefaultCursorAppSubmitter:
    async def submit(
        self,
        *,
        workspace_root: str | Path,
        prompt: str,
        command_title: str,
        submit_mode: str | None,
        start_new_composer: bool = False,
    ) -> CursorAppSubmitResult:
        return await submit_prompt_to_cursor_app(
            workspace_root=workspace_root,
            prompt=prompt,
            command_title=command_title,
            submit_mode=submit_mode,
            start_new_composer=start_new_composer,
        )


def build_cursor_app_submit_command(config: TextStreamConfig) -> list[str]:
    workspace_root = config.working_directory or os.getcwd()
    script_path = REPOLINE_ROOT / "scripts" / "cursor_app_submit.py"
    return [
        sys.executable,
        str(script_path),
        "--workspace",
        str(Path(workspace_root).expanduser().resolve()),
        "--command-title",
        DEFAULT_CURSOR_APP_COMMAND_TITLE,
        "--prompt",
        _build_cursor_app_prompt(config),
        *(
            ["--submit-mode", config.provider_submit_mode]
            if config.provider_submit_mode
            else []
        ),
        *(["--new-composer"] if config.fresh_session_strategy == "new_composer" else []),
    ]


class CursorAppTransport:
    def __init__(
        self,
        *,
        submitter: CursorAppSubmitter | None = None,
        composer_id_resolver: Callable[[str | Path], str] = find_active_composer_id,
        tail_factory: Callable[[str], CursorComposerTailProtocol] | None = None,
        bubble_loader: Callable[[str], list[Any]] = load_bubbles,
        composer_loader: Callable[[str], dict[str, Any]] = load_composer_data,
        poll_interval_seconds: float = APP_STREAM_POLL_INTERVAL_SECONDS,
        settle_delay_seconds: float = APP_SETTLE_DELAY_SECONDS,
        response_timeout_seconds: float = APP_RESPONSE_TIMEOUT_SECONDS,
    ) -> None:
        self._submitter = submitter or DefaultCursorAppSubmitter()
        self._composer_id_resolver = composer_id_resolver
        self._tail_factory = tail_factory or (lambda composer_id: CursorComposerTail(composer_id))
        self._bubble_loader = bubble_loader
        self._composer_loader = composer_loader
        self._poll_interval_seconds = poll_interval_seconds
        self._settle_delay_seconds = settle_delay_seconds
        self._response_timeout_seconds = response_timeout_seconds

    async def stream(self, config: TextStreamConfig) -> AsyncIterator[TextStreamEvent]:
        provider_name = provider_display_name("cursor", transport="app")
        workspace_root = str(Path(config.working_directory or os.getcwd()).expanduser().resolve())
        prompt = _build_cursor_app_prompt(config)
        requested_composer_id = (
            config.resume_session_id
            or config.session_id
            or self._composer_id_resolver(workspace_root)
        )
        chunker = SentenceChunker(config.chunk_chars)
        assistant_text = ""
        last_activity_at = time.monotonic()
        saw_assistant = False

        yield TextStreamEvent(
            type="status",
            message=f"Starting {provider_name} stream.",
            session_id=requested_composer_id,
        )

        try:
            submit_result = await self._submitter.submit(
                workspace_root=workspace_root,
                prompt=prompt,
                command_title=DEFAULT_CURSOR_APP_COMMAND_TITLE,
                submit_mode=config.provider_submit_mode,
                start_new_composer=(
                    config.resume_session_id is None
                    and config.fresh_session_strategy == "new_composer"
                ),
            )
        except CursorAppSubmitError as exc:
            raise TextStreamError(str(exc)) from exc

        composer_id = submit_result.composer_id
        tail = self._tail_factory(composer_id)
        with suppress(Exception):
            tail.seed_known_bubbles(
                _seed_bubbles_before_submitted_response(
                    self._bubble_loader(composer_id),
                    submitted_user_bubble_id=submit_result.user_bubble_id,
                    prompt=prompt,
                )
            )

        yield TextStreamEvent(
            type="status",
            message=f"{provider_name} submitted the turn.",
            session_id=composer_id,
        )

        while True:
            updates = tail.snapshot_updates(include_existing=not saw_assistant)
            if updates:
                last_activity_at = time.monotonic()

            for update in updates:
                bubble = update.bubble
                if bubble.role != "assistant":
                    continue

                if bubble.is_tool_event:
                    artifact = _tool_artifact_from_bubble(bubble.raw)
                    if artifact is not None:
                        yield TextStreamEvent(
                            type="artifact",
                            artifact=artifact,
                            session_id=composer_id,
                        )
                    continue

                delta_text = update.delta_text or bubble.text
                if not delta_text:
                    continue

                saw_assistant = True
                yield TextStreamEvent(
                    type="assistant_delta",
                    text=delta_text,
                    session_id=composer_id,
                    trace={
                        "composer_id": composer_id,
                        "bubble_id": bubble.bubble_id,
                        "request_id": bubble.request_id,
                        "kind": getattr(update, "kind", "update"),
                    },
                )
                assistant_text += delta_text
                for chunk in chunker.feed(delta_text):
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=False,
                        session_id=composer_id,
                    )

            try:
                composer_data = self._composer_loader(composer_id)
            except Exception as exc:
                raise TextStreamError(
                    f"{provider_name} could not read composer state."
                ) from exc
            status = str(composer_data.get("status") or "").strip().lower()
            generating = composer_data.get("generatingBubbleIds")
            is_settled = status == "completed" and not generating

            if (
                saw_assistant
                and is_settled
                and time.monotonic() - last_activity_at >= self._settle_delay_seconds
            ):
                for chunk in chunker.flush():
                    yield TextStreamEvent(
                        type="speech_chunk",
                        text=chunk,
                        final=True,
                        session_id=composer_id,
                    )
                for artifact in iter_final_text_artifacts(
                    assistant_text,
                    artifact_id_prefix=f"cursor-app:{composer_id}:assistant",
                ):
                    yield TextStreamEvent(
                        type="artifact",
                        artifact=artifact,
                        session_id=composer_id,
                    )
                yield TextStreamEvent(
                    type="done",
                    exit_code=0,
                    session_id=composer_id,
                )
                return

            if not saw_assistant and time.monotonic() - last_activity_at >= self._response_timeout_seconds:
                raise TextStreamError(
                    f"{provider_name} did not produce assistant output within {self._response_timeout_seconds:.0f} seconds."
                )

            await asyncio.sleep(self._poll_interval_seconds)


def _build_cursor_app_prompt(config: TextStreamConfig) -> str:
    prompt = config.prompt.strip()
    prefix = VOICE_MODE_HINT
    if config.access_policy == "readonly":
        prefix = (
            f"{prefix} Readonly session. Do not edit files. "
            "If the user asks for edits, say briefly that this session is readonly. "
            "Do not mention readonly otherwise."
        )
    return f"{prefix}\n\n{prompt}"


def _tool_artifact_from_bubble(raw: dict[str, Any]) -> UiArtifact | None:
    tool_data = raw.get("toolFormerData")
    if not isinstance(tool_data, dict):
        return None

    client_side_tool = tool_data.get("clientSideTool")
    tool_name = str(client_side_tool or tool_data.get("name") or "Tool").strip()
    tool_name = tool_name.replace("_", " ").replace("-", " ").title()

    params = tool_data.get("params")
    if isinstance(params, dict) and params:
        text = "\n".join(f"{key}: {value}" for key, value in sorted(params.items()))
    else:
        text = ""

    return UiArtifact(
        kind="tool",
        title=tool_name or "Tool",
        text=text,
        artifact_id=str(raw.get("bubbleId") or ""),
    )


def _seed_bubbles_before_submitted_response(
    bubbles: list[Any],
    *,
    submitted_user_bubble_id: str | None = None,
    prompt: str,
) -> list[Any]:
    if submitted_user_bubble_id:
        for index, bubble in enumerate(bubbles):
            bubble_id = str(getattr(bubble, "bubble_id", "") or "").strip()
            if bubble_id == submitted_user_bubble_id:
                return bubbles[: index + 1]

    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        return bubbles

    last_matching_user_index: int | None = None
    for index, bubble in enumerate(bubbles):
        if getattr(bubble, "role", None) != "user":
            continue
        bubble_text = str(getattr(bubble, "text", "") or "").strip()
        if bubble_text == normalized_prompt:
            last_matching_user_index = index

    if last_matching_user_index is None:
        return bubbles

    return bubbles[: last_matching_user_index + 1]
