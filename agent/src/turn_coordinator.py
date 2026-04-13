from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from bridge_config import BridgeConfig
from model_stream import (
    TextStreamConfig,
    TextStreamError,
    TextStreamEvent,
    provider_display_name,
    stream_text_events,
)
from telemetry import BridgeTelemetry
from turn_strategy import join_transcript_parts, resolve_pending_turn_delay_seconds

logger = logging.getLogger("repoline-bridge")


class SpeechHandle(Protocol):
    def done(self) -> bool: ...

    def interrupt(self, *, force: bool = False) -> None: ...

    async def wait_for_playout(self) -> None: ...


class TurnSession(Protocol):
    def say(
        self,
        content: str | AsyncIterator[str],
        *,
        allow_interruptions: bool = True,
        add_to_chat_ctx: bool = True,
    ) -> SpeechHandle: ...

    async def publish_artifact(
        self, text: str, attributes: dict[str, str]
    ) -> None: ...


StreamEventsFactory = Callable[[TextStreamConfig], AsyncIterator[TextStreamEvent]]
SleepFn = Callable[[float], Awaitable[None]]
MonotonicFn = Callable[[], float]


@dataclass(frozen=True, slots=True)
class TurnCoordinatorConfig:
    provider: str
    chunk_chars: int
    model: str | None
    thinking_level: str | None
    system_prompt: str
    working_directory: str
    access_policy: str
    final_transcript_debounce_seconds: float
    short_transcript_word_threshold: int
    short_transcript_debounce_seconds: float

    @classmethod
    def from_bridge_config(cls, config: BridgeConfig) -> TurnCoordinatorConfig:
        return cls(
            provider=config.provider,
            chunk_chars=config.chunk_chars,
            model=config.model,
            thinking_level=config.thinking_level,
            system_prompt=config.system_prompt,
            working_directory=config.working_directory,
            access_policy=config.access_policy,
            final_transcript_debounce_seconds=config.final_transcript_debounce_seconds,
            short_transcript_word_threshold=config.short_transcript_word_threshold,
            short_transcript_debounce_seconds=config.short_transcript_debounce_seconds,
        )


class TurnCoordinator:
    def __init__(
        self,
        *,
        config: TurnCoordinatorConfig,
        session: TurnSession,
        telemetry: BridgeTelemetry,
        stream_events: StreamEventsFactory = stream_text_events,
        sleep: SleepFn = asyncio.sleep,
        monotonic: MonotonicFn = time.monotonic,
    ) -> None:
        self._config = config
        self._session = session
        self._telemetry = telemetry
        self._stream_events = stream_events
        self._sleep = sleep
        self._monotonic = monotonic

        self._active_turn_task: asyncio.Task[None] | None = None
        self._active_speech: SpeechHandle | None = None
        self._pending_turn_task: asyncio.Task[None] | None = None
        self._pending_user_parts: list[str] = []
        self._pending_turn_id: str | None = None
        self._pending_last_transcript_at = 0.0
        self._last_completed_stream_session_id: str | None = None
        self._turn_lock = asyncio.Lock()

    def on_user_input_transcribed(self, transcript: str, *, is_final: bool) -> None:
        text = transcript.strip()
        if not text:
            return

        if is_final and self._pending_turn_id is None:
            self._pending_turn_id = str(uuid.uuid4())
            self._telemetry.emit("turn_opened", turn_id=self._pending_turn_id, transcript=text)

        if self._pending_turn_id is not None:
            self._pending_last_transcript_at = self._monotonic()

        self._telemetry.emit(
            "user_input_transcribed",
            turn_id=self._pending_turn_id,
            is_final=is_final,
            transcript=text,
        )

        if not is_final:
            return

        logger.info("Final transcript: %s", text)
        self._pending_user_parts.append(text)

        if self._pending_turn_task is None or self._pending_turn_task.done():
            self._pending_turn_task = asyncio.create_task(self._flush_pending_turn())

    async def submit_text_turn(
        self,
        user_text: str,
        *,
        source: str,
        participant_identity: str | None = None,
        message_id: str | None = None,
    ) -> None:
        text = user_text.strip()
        if not text:
            return

        turn_id = str(uuid.uuid4())
        await self._stop_pending_turn()

        logger.info("Starting %s turn from %s input: %s", self._config.provider, source, text)
        self._telemetry.emit(
            "turn_opened",
            turn_id=turn_id,
            transcript=text,
            input_source=source,
            participant_identity=participant_identity,
            message_id=message_id,
        )
        self._telemetry.emit(
            "user_input_received",
            turn_id=turn_id,
            transcript=text,
            input_source=source,
            participant_identity=participant_identity,
            message_id=message_id,
        )
        await self._start_turn(turn_id, text)

    async def shutdown(self) -> None:
        await self._stop_pending_turn()
        await self._stop_active_turn()

    async def _stop_active_turn(self) -> None:
        if self._active_speech is not None and not self._active_speech.done():
            with contextlib.suppress(RuntimeError):
                self._active_speech.interrupt(force=True)
            with contextlib.suppress(Exception):
                await self._active_speech.wait_for_playout()
        self._active_speech = None

        if self._active_turn_task is not None and not self._active_turn_task.done():
            self._active_turn_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._active_turn_task
        self._active_turn_task = None

    async def _stop_pending_turn(self) -> None:
        if self._pending_turn_task is not None and not self._pending_turn_task.done():
            self._pending_turn_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending_turn_task
        self._pending_turn_task = None

        self._pending_user_parts.clear()
        self._pending_turn_id = None
        self._pending_last_transcript_at = 0.0

    async def _start_turn(self, turn_id: str, user_text: str) -> None:
        async with self._turn_lock:
            await self._stop_active_turn()
            self._active_turn_task = asyncio.create_task(self._run_turn(turn_id, user_text))

    async def _run_turn(self, turn_id: str, user_text: str) -> None:
        provider_name = provider_display_name(self._config.provider)
        stream_session_id = str(uuid.uuid4()) if self._config.provider == "claude" else None
        active_session_id = stream_session_id or self._last_completed_stream_session_id
        turn_completed = False
        saw_text = False
        error_message: str | None = None
        started_at = self._monotonic()

        config = TextStreamConfig(
            prompt=user_text,
            provider=self._config.provider,
            session_id=stream_session_id,
            resume_session_id=self._last_completed_stream_session_id,
            system_prompt=self._config.system_prompt,
            model=self._config.model,
            thinking_level=self._config.thinking_level,
            working_directory=self._config.working_directory,
            chunk_chars=self._config.chunk_chars,
            access_policy=self._config.access_policy,
        )

        self._telemetry.emit(
            "model_turn_started",
            turn_id=turn_id,
            provider=self._config.provider,
            stream_session_id=stream_session_id,
            resume_session_id=self._last_completed_stream_session_id,
            transcript=user_text,
        )

        event_stream = self._stream_events(config)
        speech_handle = None
        artifact_sequence = 0

        async def consume_event(event: TextStreamEvent) -> str | None:
            nonlocal active_session_id, artifact_sequence, error_message, saw_text, turn_completed

            if event.session_id:
                active_session_id = event.session_id

            if event.type == "status":
                self._telemetry.emit(
                    "model_status",
                    turn_id=turn_id,
                    provider=self._config.provider,
                    stream_session_id=active_session_id,
                    message=event.message,
                    latency_ms=round((self._monotonic() - started_at) * 1000, 1),
                )
                return None

            if event.type == "speech_chunk" and event.text:
                saw_text = True
                self._telemetry.emit(
                    "model_speech_chunk",
                    turn_id=turn_id,
                    provider=self._config.provider,
                    stream_session_id=active_session_id,
                    text=event.text,
                    final=event.final,
                    latency_ms=round((self._monotonic() - started_at) * 1000, 1),
                )
                return event.text

            if event.type == "artifact" and event.artifact and event.artifact.text.strip():
                artifact_sequence += 1
                attributes = {
                    "repoline.kind": event.artifact.kind,
                    "repoline.title": event.artifact.title,
                    "repoline.provider": self._config.provider,
                    "repoline.turn_id": turn_id,
                    "repoline.sequence": str(artifact_sequence),
                }
                if event.artifact.artifact_id:
                    attributes["repoline.artifact_id"] = event.artifact.artifact_id
                if event.artifact.language:
                    attributes["repoline.language"] = event.artifact.language
                if active_session_id:
                    attributes["repoline.session_id"] = active_session_id

                try:
                    await self._session.publish_artifact(event.artifact.text, attributes)
                    self._telemetry.emit(
                        "model_artifact_published",
                        turn_id=turn_id,
                        provider=self._config.provider,
                        stream_session_id=active_session_id,
                        kind=event.artifact.kind,
                        title=event.artifact.title,
                        language=event.artifact.language,
                        sequence=artifact_sequence,
                        latency_ms=round((self._monotonic() - started_at) * 1000, 1),
                    )
                except Exception:
                    logger.exception("failed to publish UI artifact")
                return None

            if event.type == "error":
                error_message = event.message or f"{provider_name} failed."
                self._telemetry.emit(
                    "model_error",
                    turn_id=turn_id,
                    provider=self._config.provider,
                    stream_session_id=active_session_id,
                    message=error_message,
                    exit_code=event.exit_code,
                    latency_ms=round((self._monotonic() - started_at) * 1000, 1),
                )
                return None

            if event.type == "done":
                turn_completed = error_message is None
                self._telemetry.emit(
                    "model_done",
                    turn_id=turn_id,
                    provider=self._config.provider,
                    stream_session_id=active_session_id,
                    exit_code=event.exit_code,
                    completed=turn_completed,
                    latency_ms=round((self._monotonic() - started_at) * 1000, 1),
                )

            return None

        try:
            first_chunk = None
            async for event in event_stream:
                chunk = await consume_event(event)
                if chunk:
                    first_chunk = chunk
                    break
                if error_message:
                    break

            if first_chunk is None:
                if error_message:
                    raise TextStreamError(error_message)
                raise TextStreamError(
                    f"{provider_name} finished without producing speech text."
                )

            self._telemetry.emit(
                "model_first_chunk_ready",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
                latency_ms=round((self._monotonic() - started_at) * 1000, 1),
            )

            async def speech_chunks() -> AsyncIterator[str]:
                yield first_chunk
                async for event in event_stream:
                    chunk = await consume_event(event)
                    if chunk:
                        yield chunk

            speech_handle = self._session.say(speech_chunks(), allow_interruptions=True)
            self._active_speech = speech_handle
            self._telemetry.emit(
                "tts_playout_started",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
            )
            await speech_handle.wait_for_playout()
            if turn_completed and active_session_id:
                self._last_completed_stream_session_id = active_session_id
            self._telemetry.emit(
                "tts_playout_finished",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
                latency_ms=round((self._monotonic() - started_at) * 1000, 1),
            )
        except StopAsyncIteration:
            logger.warning("%s finished without returning speech text", provider_name)
            self._telemetry.emit(
                "model_empty_turn",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
            )
        except TextStreamError as exc:
            logger.exception("%s stream failed: %s", provider_name, exc)
            message = str(exc).strip() or f"{provider_name} failed before returning a response."
            speech_handle = self._session.say(
                message,
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
            self._active_speech = speech_handle
            self._telemetry.emit(
                "model_error_spoken",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
                message=message,
            )
            await speech_handle.wait_for_playout()
        except asyncio.CancelledError:
            if speech_handle is not None and not speech_handle.done():
                with contextlib.suppress(RuntimeError):
                    speech_handle.interrupt(force=True)
            self._telemetry.emit(
                "model_turn_cancelled",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
            )
            raise
        finally:
            if turn_completed:
                logger.info(
                    "%s turn completed successfully; next turn will resume from session %s",
                    provider_name,
                    active_session_id,
                )
            self._telemetry.emit(
                "model_turn_finished",
                turn_id=turn_id,
                provider=self._config.provider,
                stream_session_id=active_session_id,
                completed=turn_completed,
                saw_text=saw_text,
                error_message=error_message,
                latency_ms=round((self._monotonic() - started_at) * 1000, 1),
            )
            if self._active_speech is speech_handle:
                self._active_speech = None

    async def _flush_pending_turn(self) -> None:
        current_task = asyncio.current_task()

        try:
            debounce_seconds = self._config.final_transcript_debounce_seconds
            while True:
                debounce_seconds = resolve_pending_turn_delay_seconds(
                    self._pending_user_parts,
                    base_delay_seconds=self._config.final_transcript_debounce_seconds,
                    short_transcript_delay_seconds=self._config.short_transcript_debounce_seconds,
                    short_transcript_word_threshold=self._config.short_transcript_word_threshold,
                )
                remaining = (
                    self._pending_last_transcript_at + debounce_seconds
                ) - self._monotonic()
                if remaining > 0:
                    await self._sleep(remaining)
                    continue
                break

            text = join_transcript_parts(self._pending_user_parts)
            turn_id = self._pending_turn_id or str(uuid.uuid4())
            self._pending_turn_id = None
            self._pending_user_parts.clear()
            self._pending_last_transcript_at = 0.0
            if not text:
                return
            logger.info(
                "Starting %s turn with merged transcript: %s",
                self._config.provider,
                text,
            )
            self._telemetry.emit(
                "turn_merged",
                turn_id=turn_id,
                transcript=text,
                debounce_seconds=debounce_seconds,
            )
            await self._start_turn(turn_id, text)
        except asyncio.CancelledError:
            raise
        finally:
            if self._pending_turn_task is current_task:
                self._pending_turn_task = None
