from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    inference,
)
from livekit.agents.metrics import log_metrics
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from model_stream import (
    TextStreamConfig,
    TextStreamError,
    infer_access_policy,
    normalize_provider,
    provider_display_name,
    stream_text_events,
)
from repoline_skill import (
    DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    resolve_repoline_skill_prompt,
)
from telemetry import BridgeTelemetry
from turn_strategy import join_transcript_parts, resolve_pending_turn_delay_seconds
from voice_behavior import build_followup_status_message, build_initial_status_message

logger = logging.getLogger("repoline-bridge")
REPOLINE_UI_ARTIFACT_TOPIC = "repoline.ui.artifact"

load_dotenv(".env.local")


def _resolve_bridge_system_prompt() -> str:
    provider = normalize_provider(os.environ["BRIDGE_CLI_PROVIDER"])
    working_directory = os.environ["BRIDGE_WORKDIR"]
    skill_name = os.environ["REPOLINE_SKILL_NAME"]
    tts_pronunciation_skill_name = os.getenv(
        "REPOLINE_TTS_PRONUNCIATION_SKILL_NAME",
        DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    )

    return resolve_repoline_skill_prompt(
        provider=provider,
        working_directory=working_directory,
        explicit_system_prompt=os.getenv("BRIDGE_SYSTEM_PROMPT"),
        skill_name=skill_name,
        tts_pronunciation_skill_name=tts_pronunciation_skill_name,
    ).prompt


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return int(value)


def _env_optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_optional_bool(name: str) -> bool | None:
    value = _env_optional(name)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def _resolve_thinking_level() -> str | None:
    return (
        _env_optional("BRIDGE_THINKING_LEVEL")
        or _env_optional("BRIDGE_CODEX_REASONING_EFFORT")
        or "low"
    )


def _resolve_access_policy(provider: str) -> str:
    return infer_access_policy(
        normalize_provider(provider),
        _env_optional("BRIDGE_ACCESS_POLICY"),
        legacy_codex_bypass=_env_optional_bool(
            "CODEX_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX"
        ),
        legacy_cursor_force=_env_optional_bool("BRIDGE_CURSOR_FORCE"),
        legacy_cursor_approve_mcps=_env_optional_bool("BRIDGE_CURSOR_APPROVE_MCPS"),
        legacy_cursor_sandbox_mode=_env_optional("BRIDGE_CURSOR_SANDBOX"),
    )


@dataclass(frozen=True, slots=True)
class BridgeSettings:
    agent_name: str = os.getenv("LIVEKIT_AGENT_NAME", "clawdbot-agent")
    greeting: str = os.getenv(
        "BRIDGE_GREETING",
        "RepoLine is live. What do you want to work on?",
    )
    provider: str = normalize_provider(os.environ["BRIDGE_CLI_PROVIDER"])
    skill_name: str = os.environ["REPOLINE_SKILL_NAME"]
    tts_pronunciation_skill_name: str = os.getenv(
        "REPOLINE_TTS_PRONUNCIATION_SKILL_NAME",
        DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    )
    chunk_chars: int = int(os.getenv("BRIDGE_CHUNK_CHARS", "140"))
    model: str | None = _env_optional("BRIDGE_MODEL")
    thinking_level: str | None = _resolve_thinking_level()
    system_prompt: str = _resolve_bridge_system_prompt()
    working_directory: str = os.environ["BRIDGE_WORKDIR"]
    access_policy: str = _resolve_access_policy(os.environ["BRIDGE_CLI_PROVIDER"])
    final_transcript_debounce_seconds: float = float(
        os.getenv("FINAL_TRANSCRIPT_DEBOUNCE_SECONDS", "0.85")
    )
    short_transcript_word_threshold: int = int(
        os.getenv("BRIDGE_SHORT_TRANSCRIPT_WORDS", "2")
    )
    short_transcript_debounce_seconds: float = float(
        os.getenv("BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS", "2.75")
    )
    status_speech_enabled: bool = _env_bool("BRIDGE_STATUS_SPEECH_ENABLED", True)
    status_speech_delay_seconds: float = float(
        os.getenv("BRIDGE_STATUS_SPEECH_DELAY_SECONDS", "0.15")
    )
    status_followup_delay_seconds: float = float(
        os.getenv("BRIDGE_STATUS_FOLLOWUP_DELAY_SECONDS", "4.0")
    )
    status_followup_interval_seconds: float = float(
        os.getenv("BRIDGE_STATUS_FOLLOWUP_INTERVAL_SECONDS", "8.0")
    )
    telemetry_jsonl_path: str | None = os.getenv("BRIDGE_TELEMETRY_JSONL") or str(
        Path(__file__).resolve().parent.parent / "logs" / "bridge-telemetry.jsonl"
    )
    livekit_record_audio: bool = _env_bool("LIVEKIT_RECORD_AUDIO", False)
    livekit_record_traces: bool = _env_bool("LIVEKIT_RECORD_TRACES", True)
    livekit_record_logs: bool = _env_bool("LIVEKIT_RECORD_LOGS", True)
    livekit_record_transcript: bool = _env_bool("LIVEKIT_RECORD_TRANSCRIPT", True)
    prometheus_port: int | None = _env_int("BRIDGE_PROMETHEUS_PORT")
    stt_model: str = os.getenv("LIVEKIT_STT_MODEL", "deepgram/nova-3")
    stt_language: str = os.getenv("LIVEKIT_STT_LANGUAGE", "multi")
    turn_endpointing_mode: str = os.getenv("LIVEKIT_TURN_ENDPOINTING_MODE", "dynamic")
    turn_min_endpointing_delay_seconds: float = float(
        os.getenv("LIVEKIT_TURN_MIN_ENDPOINTING_DELAY_SECONDS", "0.8")
    )
    turn_max_endpointing_delay_seconds: float = float(
        os.getenv("LIVEKIT_TURN_MAX_ENDPOINTING_DELAY_SECONDS", "2.2")
    )
    turn_interruption_mode: str = os.getenv(
        "LIVEKIT_TURN_INTERRUPTION_MODE", "adaptive"
    )
    false_interruption_timeout_seconds: float = float(
        os.getenv("LIVEKIT_FALSE_INTERRUPTION_TIMEOUT_SECONDS", "1.5")
    )
    resume_false_interruption: bool = _env_bool(
        "LIVEKIT_RESUME_FALSE_INTERRUPTION", True
    )
    tts_model: str = os.getenv("LIVEKIT_TTS_MODEL", "cartesia/sonic-3")
    tts_voice: str = os.getenv(
        "LIVEKIT_TTS_VOICE",
        "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
    )


SETTINGS = BridgeSettings()
SERVER = AgentServer(prometheus_port=SETTINGS.prometheus_port)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


SERVER.setup_fnc = prewarm


def _new_agent() -> Agent:
    return Agent(
        instructions=(
            "You are the transport layer for a RepoLine voice bridge. "
            "LiveKit handles audio; the configured coding CLI handles the actual replies."
        )
    )


@SERVER.rtc_session(agent_name=SETTINGS.agent_name)
async def coding_cli_bridge(ctx: JobContext) -> None:
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "provider": SETTINGS.provider,
        "workdir": SETTINGS.working_directory,
    }
    telemetry = BridgeTelemetry(SETTINGS.telemetry_jsonl_path)
    telemetry.emit(
        "bridge_session_started",
        room=ctx.room.name,
        livekit_url=os.getenv("LIVEKIT_URL"),
        provider=SETTINGS.provider,
        model=SETTINGS.model,
        workdir=SETTINGS.working_directory,
        stt_model=SETTINGS.stt_model,
        stt_language=SETTINGS.stt_language,
        turn_endpointing_mode=SETTINGS.turn_endpointing_mode,
        turn_min_endpointing_delay_seconds=SETTINGS.turn_min_endpointing_delay_seconds,
        turn_max_endpointing_delay_seconds=SETTINGS.turn_max_endpointing_delay_seconds,
        turn_interruption_mode=SETTINGS.turn_interruption_mode,
        tts_model=SETTINGS.tts_model,
    )

    session = AgentSession(
        stt=inference.STT(
            model=SETTINGS.stt_model,
            language=SETTINGS.stt_language,
        ),
        tts=inference.TTS(
            model=SETTINGS.tts_model,
            voice=SETTINGS.tts_voice,
        ),
        turn_handling={
            "turn_detection": MultilingualModel(),
            "endpointing": {
                "mode": SETTINGS.turn_endpointing_mode,
                "min_delay": SETTINGS.turn_min_endpointing_delay_seconds,
                "max_delay": SETTINGS.turn_max_endpointing_delay_seconds,
            },
            "interruption": {
                "mode": SETTINGS.turn_interruption_mode,
                "false_interruption_timeout": SETTINGS.false_interruption_timeout_seconds,
                "resume_false_interruption": SETTINGS.resume_false_interruption,
            },
        },
        vad=ctx.proc.userdata["vad"],
    )

    agent = _new_agent()
    active_turn_task: asyncio.Task[None] | None = None
    active_speech = None
    pending_turn_task: asyncio.Task[None] | None = None
    pending_status_task: asyncio.Task[None] | None = None
    pending_status_speech = None
    pending_user_parts: list[str] = []
    pending_turn_id: str | None = None
    pending_last_transcript_at = 0.0
    pending_status_announced = False
    last_completed_stream_session_id: str | None = None
    turn_lock = asyncio.Lock()

    async def stop_active_turn() -> None:
        nonlocal active_turn_task, active_speech

        if active_speech is not None and not active_speech.done():
            with contextlib.suppress(RuntimeError):
                active_speech.interrupt(force=True)
            with contextlib.suppress(Exception):
                await active_speech.wait_for_playout()
        active_speech = None

        if active_turn_task is not None and not active_turn_task.done():
            active_turn_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_turn_task
        active_turn_task = None

    async def stop_pending_status() -> None:
        nonlocal pending_status_task, pending_status_speech

        if pending_status_speech is not None and not pending_status_speech.done():
            with contextlib.suppress(RuntimeError):
                pending_status_speech.interrupt(force=True)
            with contextlib.suppress(Exception):
                await pending_status_speech.wait_for_playout()
        pending_status_speech = None

        if pending_status_task is not None and not pending_status_task.done():
            pending_status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending_status_task
        pending_status_task = None

    async def maybe_speak_pending_status(turn_id: str) -> None:
        nonlocal pending_status_announced, pending_status_speech

        if not SETTINGS.status_speech_enabled:
            return

        speech_handle = None
        try:
            await asyncio.sleep(SETTINGS.status_speech_delay_seconds)

            if pending_turn_id != turn_id:
                return

            transcript_preview = join_transcript_parts(pending_user_parts)
            message = build_initial_status_message(transcript_preview)
            telemetry.emit(
                "bridge_status_started",
                turn_id=turn_id,
                transcript=transcript_preview,
                message=message,
            )
            pending_status_announced = True
            speech_handle = session.say(
                message,
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
            pending_status_speech = speech_handle
            await speech_handle.wait_for_playout()
            telemetry.emit("bridge_status_completed", turn_id=turn_id, message=message)
        except asyncio.CancelledError:
            raise
        finally:
            if pending_status_speech is speech_handle:
                pending_status_speech = None

    async def run_turn(turn_id: str, user_text: str) -> None:
        nonlocal active_speech, last_completed_stream_session_id

        provider_name = provider_display_name(SETTINGS.provider)
        stream_session_id = str(uuid.uuid4()) if SETTINGS.provider == "claude" else None
        active_session_id = stream_session_id or last_completed_stream_session_id
        turn_completed = False
        saw_text = False
        error_message: str | None = None
        started_at = time.monotonic()

        config = TextStreamConfig(
            prompt=user_text,
            provider=SETTINGS.provider,
            session_id=stream_session_id,
            resume_session_id=last_completed_stream_session_id,
            system_prompt=SETTINGS.system_prompt,
            model=SETTINGS.model,
            thinking_level=SETTINGS.thinking_level,
            working_directory=SETTINGS.working_directory,
            chunk_chars=SETTINGS.chunk_chars,
            access_policy=SETTINGS.access_policy,
        )

        telemetry.emit(
            "model_turn_started",
            turn_id=turn_id,
            provider=SETTINGS.provider,
            stream_session_id=stream_session_id,
            resume_session_id=last_completed_stream_session_id,
            transcript=user_text,
        )

        event_stream = stream_text_events(config)
        speech_handle = None
        followup_status_task: asyncio.Task[None] | None = None
        followup_status_speech = None
        followup_status_count = 0
        artifact_sequence = 0

        async def stop_followup_status() -> None:
            nonlocal followup_status_task, followup_status_speech

            if followup_status_speech is not None and not followup_status_speech.done():
                with contextlib.suppress(RuntimeError):
                    followup_status_speech.interrupt(force=True)
                with contextlib.suppress(Exception):
                    await followup_status_speech.wait_for_playout()
            followup_status_speech = None

            if followup_status_task is not None and not followup_status_task.done():
                followup_status_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await followup_status_task
            followup_status_task = None

        async def maybe_speak_followup_status() -> None:
            nonlocal followup_status_count, followup_status_speech

            if not SETTINGS.status_speech_enabled:
                return

            await asyncio.sleep(SETTINGS.status_followup_delay_seconds)

            while True:
                message = build_followup_status_message(
                    user_text, followup_status_count
                )
                followup_status_count += 1
                telemetry.emit(
                    "bridge_status_followup_started",
                    turn_id=turn_id,
                    transcript=user_text,
                    message=message,
                )
                speech_handle = session.say(
                    message,
                    allow_interruptions=True,
                    add_to_chat_ctx=False,
                )
                followup_status_speech = speech_handle
                try:
                    await speech_handle.wait_for_playout()
                    telemetry.emit(
                        "bridge_status_followup_completed",
                        turn_id=turn_id,
                        message=message,
                    )
                finally:
                    if followup_status_speech is speech_handle:
                        followup_status_speech = None

                await asyncio.sleep(SETTINGS.status_followup_interval_seconds)

        async def consume_event(event) -> str | None:
            nonlocal \
                active_session_id, \
                artifact_sequence, \
                error_message, \
                saw_text, \
                turn_completed

            if event.session_id:
                active_session_id = event.session_id

            if event.type == "status":
                telemetry.emit(
                    "model_status",
                    turn_id=turn_id,
                    provider=SETTINGS.provider,
                    stream_session_id=active_session_id,
                    message=event.message,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )
                return None

            if event.type == "speech_chunk" and event.text:
                saw_text = True
                telemetry.emit(
                    "model_speech_chunk",
                    turn_id=turn_id,
                    provider=SETTINGS.provider,
                    stream_session_id=active_session_id,
                    text=event.text,
                    final=event.final,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )
                return event.text

            if (
                event.type == "artifact"
                and event.artifact
                and event.artifact.text.strip()
            ):
                artifact_sequence += 1
                attributes = {
                    "repoline.kind": event.artifact.kind,
                    "repoline.title": event.artifact.title,
                    "repoline.provider": SETTINGS.provider,
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
                    await session.room_io.room.local_participant.send_text(
                        event.artifact.text,
                        topic=REPOLINE_UI_ARTIFACT_TOPIC,
                        attributes=attributes,
                    )
                    telemetry.emit(
                        "model_artifact_published",
                        turn_id=turn_id,
                        provider=SETTINGS.provider,
                        stream_session_id=active_session_id,
                        kind=event.artifact.kind,
                        title=event.artifact.title,
                        language=event.artifact.language,
                        sequence=artifact_sequence,
                        latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                    )
                except Exception:
                    logger.exception("failed to publish UI artifact")
                return None

            if event.type == "error":
                error_message = event.message or f"{provider_name} failed."
                telemetry.emit(
                    "model_error",
                    turn_id=turn_id,
                    provider=SETTINGS.provider,
                    stream_session_id=active_session_id,
                    message=error_message,
                    exit_code=event.exit_code,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )
                return None

            if event.type == "done":
                turn_completed = error_message is None
                telemetry.emit(
                    "model_done",
                    turn_id=turn_id,
                    provider=SETTINGS.provider,
                    stream_session_id=active_session_id,
                    exit_code=event.exit_code,
                    completed=turn_completed,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )

            return None

        try:
            followup_status_task = asyncio.create_task(maybe_speak_followup_status())
            first_chunk = None
            async for event in event_stream:
                chunk = await consume_event(event)
                if chunk:
                    first_chunk = chunk
                    break
                if error_message:
                    break

            if first_chunk is None:
                await stop_followup_status()
                if error_message:
                    raise TextStreamError(error_message)
                raise TextStreamError(
                    f"{provider_name} finished without producing speech text."
                )

            await stop_followup_status()
            await stop_pending_status()
            telemetry.emit(
                "model_first_chunk_ready",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
                latency_ms=round((time.monotonic() - started_at) * 1000, 1),
            )

            async def speech_chunks():
                nonlocal last_completed_stream_session_id
                yield first_chunk
                async for event in event_stream:
                    chunk = await consume_event(event)
                    if chunk:
                        yield chunk
                if turn_completed and active_session_id:
                    last_completed_stream_session_id = active_session_id

            speech_handle = session.say(
                speech_chunks(),
                allow_interruptions=True,
            )
            active_speech = speech_handle
            telemetry.emit(
                "tts_playout_started",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
            )
            await speech_handle.wait_for_playout()
            telemetry.emit(
                "tts_playout_finished",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
                latency_ms=round((time.monotonic() - started_at) * 1000, 1),
            )
        except StopAsyncIteration:
            await stop_followup_status()
            logger.warning("%s finished without returning speech text", provider_name)
            telemetry.emit(
                "model_empty_turn",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
            )
        except TextStreamError as exc:
            await stop_followup_status()
            logger.exception("%s stream failed: %s", provider_name, exc)
            message = (
                str(exc).strip()
                or f"{provider_name} failed before returning a response."
            )
            await stop_pending_status()
            speech_handle = session.say(
                message,
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
            active_speech = speech_handle
            telemetry.emit(
                "model_error_spoken",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
                message=message,
            )
            await speech_handle.wait_for_playout()
        except asyncio.CancelledError:
            await stop_followup_status()
            if speech_handle is not None and not speech_handle.done():
                with contextlib.suppress(RuntimeError):
                    speech_handle.interrupt(force=True)
            telemetry.emit(
                "model_turn_cancelled",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
            )
            raise
        finally:
            await stop_followup_status()
            if turn_completed:
                logger.info(
                    "%s turn completed successfully; next turn will resume from session %s",
                    provider_name,
                    active_session_id,
                )
            telemetry.emit(
                "model_turn_finished",
                turn_id=turn_id,
                provider=SETTINGS.provider,
                stream_session_id=active_session_id,
                completed=turn_completed,
                saw_text=saw_text,
                error_message=error_message,
                latency_ms=round((time.monotonic() - started_at) * 1000, 1),
            )
            if active_speech is speech_handle:
                active_speech = None

    async def start_turn(turn_id: str, user_text: str) -> None:
        nonlocal active_turn_task

        async with turn_lock:
            await stop_active_turn()
            active_turn_task = asyncio.create_task(run_turn(turn_id, user_text))

    async def flush_pending_turn() -> None:
        nonlocal pending_last_transcript_at, pending_turn_id, pending_turn_task
        current_task = asyncio.current_task()

        try:
            debounce_seconds = SETTINGS.final_transcript_debounce_seconds
            while True:
                debounce_seconds = resolve_pending_turn_delay_seconds(
                    pending_user_parts,
                    base_delay_seconds=SETTINGS.final_transcript_debounce_seconds,
                    short_transcript_delay_seconds=SETTINGS.short_transcript_debounce_seconds,
                    short_transcript_word_threshold=SETTINGS.short_transcript_word_threshold,
                )
                remaining = (
                    pending_last_transcript_at + debounce_seconds
                ) - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    continue
                break

            text = join_transcript_parts(pending_user_parts)
            turn_id = pending_turn_id or str(uuid.uuid4())
            pending_turn_id = None
            pending_user_parts.clear()
            pending_last_transcript_at = 0.0
            if not text:
                await stop_pending_status()
                return
            logger.info(
                "Starting %s turn with merged transcript: %s", SETTINGS.provider, text
            )
            telemetry.emit(
                "turn_merged",
                turn_id=turn_id,
                transcript=text,
                debounce_seconds=debounce_seconds,
            )
            await start_turn(turn_id, text)
        except asyncio.CancelledError:
            raise
        finally:
            if pending_turn_task is current_task:
                pending_turn_task = None

    @session.on("agent_state_changed")
    def on_agent_state_changed(event) -> None:
        telemetry.emit(
            "agent_state_changed",
            old_state=event.old_state,
            new_state=event.new_state,
        )

    @session.on("user_state_changed")
    def on_user_state_changed(event) -> None:
        telemetry.emit(
            "user_state_changed",
            old_state=event.old_state,
            new_state=event.new_state,
        )

    @session.on("metrics_collected")
    def on_metrics_collected(event) -> None:
        log_metrics(event.metrics, logger=logger)
        telemetry.emit(
            "livekit_metrics_collected",
            metric_type=type(event.metrics).__name__,
            metrics=event.metrics,
        )

    @session.on("session_usage_updated")
    def on_session_usage_updated(event) -> None:
        telemetry.emit("livekit_session_usage_updated", usage=event.usage)

    @session.on("speech_created")
    def on_speech_created(event) -> None:
        telemetry.emit(
            "livekit_speech_created",
            source=event.source,
            user_initiated=event.user_initiated,
        )

    @session.on("error")
    def on_error(event) -> None:
        telemetry.emit(
            "livekit_error",
            source=type(event.source).__name__,
            error=event.error,
        )

    @session.on("close")
    def on_close(event) -> None:
        telemetry.emit(
            "livekit_session_closed",
            reason=event.reason,
            error=event.error,
        )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(transcript) -> None:
        nonlocal \
            pending_last_transcript_at, \
            pending_status_announced, \
            pending_status_task, \
            pending_turn_id, \
            pending_turn_task

        text = transcript.transcript.strip()
        if not text:
            return

        if transcript.is_final and pending_turn_id is None:
            pending_turn_id = str(uuid.uuid4())
            pending_status_announced = False
            telemetry.emit("turn_opened", turn_id=pending_turn_id, transcript=text)

        if pending_turn_id is not None:
            pending_last_transcript_at = time.monotonic()

        telemetry.emit(
            "user_input_transcribed",
            turn_id=pending_turn_id,
            is_final=transcript.is_final,
            transcript=text,
        )

        if not transcript.is_final:
            if pending_status_task is not None and not pending_status_task.done():
                pending_status_task.cancel()
                pending_status_task = None
            if active_speech is not None and not active_speech.done():
                with contextlib.suppress(RuntimeError):
                    active_speech.interrupt(force=True)
            if pending_status_speech is not None and not pending_status_speech.done():
                with contextlib.suppress(RuntimeError):
                    pending_status_speech.interrupt(force=True)
            return

        logger.info("Final transcript: %s", text)
        pending_user_parts.append(text)

        if (
            not pending_status_announced
            and (pending_status_task is None or pending_status_task.done())
            and pending_turn_id is not None
        ):
            pending_status_task = asyncio.create_task(
                maybe_speak_pending_status(pending_turn_id)
            )

        if pending_turn_task is None or pending_turn_task.done():
            pending_turn_task = asyncio.create_task(flush_pending_turn())

    await session.start(
        agent=agent,
        room=ctx.room,
        record={
            "audio": SETTINGS.livekit_record_audio,
            "traces": SETTINGS.livekit_record_traces,
            "logs": SETTINGS.livekit_record_logs,
            "transcript": SETTINGS.livekit_record_transcript,
        },
    )
    await ctx.connect()

    greeting = session.say(SETTINGS.greeting, add_to_chat_ctx=False)
    await greeting.wait_for_playout()


if __name__ == "__main__":
    cli.run_app(SERVER)
