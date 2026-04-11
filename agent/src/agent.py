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
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli, inference
from livekit.agents.metrics import log_metrics
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from claude_stream import ClaudeStreamConfig, ClaudeStreamError, stream_claude_events
from telemetry import BridgeTelemetry
from voice_behavior import build_initial_status_message


logger = logging.getLogger("claude-code-phone-bridge")

load_dotenv(".env.local")


DEFAULT_SYSTEM_PROMPT = (
    "You are speaking aloud through a LiveKit voice session connected to Claude Code. "
    "Keep replies concise, conversational, and easy to follow by ear. "
    "Avoid markdown, bullet lists, tables, and code fences unless the user explicitly asks. "
    "Before you inspect files, run commands, call tools, or pause for deeper reasoning, first say "
    "one short sentence about exactly what you are about to check. "
    "If the task is deep, broad, or likely to take more than a few seconds, prefer delegating "
    "background investigation to subagents when available, then say what you delegated before "
    "continuing. While work is in progress, keep giving short spoken progress updates instead of "
    "going silent."
)


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


@dataclass(frozen=True, slots=True)
class BridgeSettings:
    agent_name: str = os.getenv("LIVEKIT_AGENT_NAME", "clawdbot-agent")
    greeting: str = os.getenv(
        "BRIDGE_GREETING",
        "Claude Code phone bridge is live. What do you want to work on?",
    )
    chunk_chars: int = int(os.getenv("CLAUDE_CHUNK_CHARS", "140"))
    model: str | None = os.getenv("CLAUDE_MODEL") or None
    system_prompt: str = os.getenv("CLAUDE_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    working_directory: str = os.getenv("CLAUDE_WORKDIR") or str(Path.home())
    final_transcript_debounce_seconds: float = float(
        os.getenv("FINAL_TRANSCRIPT_DEBOUNCE_SECONDS", "0.85")
    )
    status_speech_enabled: bool = _env_bool("BRIDGE_STATUS_SPEECH_ENABLED", True)
    status_speech_delay_seconds: float = float(
        os.getenv("BRIDGE_STATUS_SPEECH_DELAY_SECONDS", "0.15")
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
            "You are the transport layer for a Claude Code voice bridge. "
            "LiveKit handles audio; Claude Code handles the actual replies."
        )
    )


@SERVER.rtc_session(agent_name=SETTINGS.agent_name)
async def claude_code_bridge(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name, "workdir": SETTINGS.working_directory}
    telemetry = BridgeTelemetry(SETTINGS.telemetry_jsonl_path)
    telemetry.emit(
        "bridge_session_started",
        room=ctx.room.name,
        livekit_url=os.getenv("LIVEKIT_URL"),
        workdir=SETTINGS.working_directory,
        stt_model=SETTINGS.stt_model,
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
        turn_detection=MultilingualModel(),
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
    last_completed_claude_session_id: str | None = None
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
        nonlocal pending_status_speech

        if not SETTINGS.status_speech_enabled:
            return

        speech_handle = None
        try:
            await asyncio.sleep(SETTINGS.status_speech_delay_seconds)

            if pending_turn_id != turn_id:
                return

            transcript_preview = " ".join(part.strip() for part in pending_user_parts if part.strip())
            message = build_initial_status_message(transcript_preview)
            telemetry.emit(
                "bridge_status_started",
                turn_id=turn_id,
                transcript=transcript_preview,
                message=message,
            )
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
        nonlocal active_speech, last_completed_claude_session_id

        claude_session_id = str(uuid.uuid4())
        turn_completed = False
        saw_text = False
        error_message: str | None = None
        started_at = time.monotonic()

        config = ClaudeStreamConfig(
            prompt=user_text,
            session_id=claude_session_id,
            resume_session_id=last_completed_claude_session_id,
            system_prompt=SETTINGS.system_prompt,
            model=SETTINGS.model,
            working_directory=SETTINGS.working_directory,
            chunk_chars=SETTINGS.chunk_chars,
        )

        telemetry.emit(
            "claude_turn_started",
            turn_id=turn_id,
            claude_session_id=claude_session_id,
            resume_session_id=last_completed_claude_session_id,
            transcript=user_text,
        )

        event_stream = stream_claude_events(config)
        speech_handle = None

        async def consume_event(event) -> str | None:
            nonlocal error_message, saw_text, turn_completed

            if event.type == "status":
                telemetry.emit(
                    "claude_status",
                    turn_id=turn_id,
                    claude_session_id=claude_session_id,
                    message=event.message,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )
                return None

            if event.type == "speech_chunk" and event.text:
                saw_text = True
                telemetry.emit(
                    "claude_speech_chunk",
                    turn_id=turn_id,
                    claude_session_id=claude_session_id,
                    text=event.text,
                    final=event.final,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )
                return event.text

            if event.type == "error":
                error_message = event.message or "Claude Code failed."
                telemetry.emit(
                    "claude_error",
                    turn_id=turn_id,
                    claude_session_id=claude_session_id,
                    message=error_message,
                    exit_code=event.exit_code,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
                )
                return None

            if event.type == "done":
                turn_completed = error_message is None
                telemetry.emit(
                    "claude_done",
                    turn_id=turn_id,
                    claude_session_id=claude_session_id,
                    exit_code=event.exit_code,
                    completed=turn_completed,
                    latency_ms=round((time.monotonic() - started_at) * 1000, 1),
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
                    raise ClaudeStreamError(error_message)
                raise ClaudeStreamError("Claude Code finished without producing speech text.")

            await stop_pending_status()
            telemetry.emit(
                "claude_first_chunk_ready",
                turn_id=turn_id,
                claude_session_id=claude_session_id,
                latency_ms=round((time.monotonic() - started_at) * 1000, 1),
            )

            async def speech_chunks():
                nonlocal last_completed_claude_session_id
                yield first_chunk
                async for event in event_stream:
                    chunk = await consume_event(event)
                    if chunk:
                        yield chunk
                if turn_completed:
                    last_completed_claude_session_id = claude_session_id

            speech_handle = session.say(
                speech_chunks(),
                allow_interruptions=True,
            )
            active_speech = speech_handle
            telemetry.emit("tts_playout_started", turn_id=turn_id, claude_session_id=claude_session_id)
            await speech_handle.wait_for_playout()
            telemetry.emit(
                "tts_playout_finished",
                turn_id=turn_id,
                claude_session_id=claude_session_id,
                latency_ms=round((time.monotonic() - started_at) * 1000, 1),
            )
        except StopAsyncIteration:
            logger.warning("Claude finished without returning speech text")
            telemetry.emit("claude_empty_turn", turn_id=turn_id, claude_session_id=claude_session_id)
        except ClaudeStreamError as exc:
            logger.exception("Claude stream failed: %s", exc)
            message = str(exc).strip() or "Claude Code failed before returning a response."
            await stop_pending_status()
            speech_handle = session.say(
                message,
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
            active_speech = speech_handle
            telemetry.emit(
                "claude_error_spoken",
                turn_id=turn_id,
                claude_session_id=claude_session_id,
                message=message,
            )
            await speech_handle.wait_for_playout()
        except asyncio.CancelledError:
            if speech_handle is not None and not speech_handle.done():
                with contextlib.suppress(RuntimeError):
                    speech_handle.interrupt(force=True)
            telemetry.emit("claude_turn_cancelled", turn_id=turn_id, claude_session_id=claude_session_id)
            raise
        finally:
            if turn_completed:
                logger.info(
                    "Claude turn completed successfully; next turn will resume from session %s",
                    claude_session_id,
                )
            telemetry.emit(
                "claude_turn_finished",
                turn_id=turn_id,
                claude_session_id=claude_session_id,
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
        nonlocal pending_turn_id, pending_turn_task
        current_task = asyncio.current_task()

        try:
            await asyncio.sleep(SETTINGS.final_transcript_debounce_seconds)
            text = " ".join(part.strip() for part in pending_user_parts if part.strip()).strip()
            turn_id = pending_turn_id or str(uuid.uuid4())
            pending_turn_id = None
            pending_user_parts.clear()
            if not text:
                await stop_pending_status()
                return
            logger.info("Starting Claude turn with merged transcript: %s", text)
            telemetry.emit("turn_merged", turn_id=turn_id, transcript=text)
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
        nonlocal pending_status_task, pending_turn_id, pending_turn_task

        text = transcript.transcript.strip()
        if not text:
            return

        if transcript.is_final and pending_turn_id is None:
            pending_turn_id = str(uuid.uuid4())
            telemetry.emit("turn_opened", turn_id=pending_turn_id, transcript=text)
            if pending_status_task is not None and not pending_status_task.done():
                pending_status_task.cancel()
            pending_status_task = asyncio.create_task(maybe_speak_pending_status(pending_turn_id))

        telemetry.emit(
            "user_input_transcribed",
            turn_id=pending_turn_id,
            is_final=transcript.is_final,
            transcript=text,
        )

        if not transcript.is_final:
            if active_speech is not None and not active_speech.done():
                with contextlib.suppress(RuntimeError):
                    active_speech.interrupt(force=True)
            if pending_status_speech is not None and not pending_status_speech.done():
                with contextlib.suppress(RuntimeError):
                    pending_status_speech.interrupt(force=True)
            return

        logger.info("Final transcript: %s", text)
        pending_user_parts.append(text)

        if pending_turn_task is not None and not pending_turn_task.done():
            pending_turn_task.cancel()

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
