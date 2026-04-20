from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
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
from livekit.plugins import deepgram, elevenlabs, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from bridge_config import BridgeConfig, render_call_greeting
from telemetry import BridgeTelemetry
from turn_orchestrator import TurnInput, TurnOrchestrator, TurnOrchestratorConfig

logger = logging.getLogger("repoline-bridge")
REPOLINE_UI_ARTIFACT_TOPIC = "repoline.ui.artifact"
REPOLINE_CONTROL_TOPIC = "repoline.control"
REPOLINE_SESSION_STATE_TOPIC = "repoline.session.state"
LIVEKIT_CHAT_TOPIC = "lk.chat"
LIVEKIT_LEGACY_CHAT_TOPIC = "lk-chat-topic"

load_dotenv(".env.local")

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = BridgeConfig.load(os.environ, REPO_ROOT)
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


def _build_stt() -> object:
    if SETTINGS.stt_provider == "deepgram":
        kwargs = {
            "model": SETTINGS.stt_model,
            "language": SETTINGS.stt_language,
            "smart_format": True,
            "punctuate": True,
            "filler_words": True,
            "profanity_filter": False,
        }
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        return deepgram.STT(**kwargs)

    return inference.STT(
        model=SETTINGS.stt_model,
        language=SETTINGS.stt_language,
    )


def _build_tts() -> object:
    if SETTINGS.tts_provider == "elevenlabs":
        kwargs = {
            "voice_id": SETTINGS.tts_voice,
            "model": SETTINGS.tts_model,
            "enable_ssml_parsing": True,
        }
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        return elevenlabs.TTS(**kwargs)

    return inference.TTS(
        model=SETTINGS.tts_model,
        voice=SETTINGS.tts_voice,
    )


class LiveKitTurnSession:
    def __init__(self, session: AgentSession) -> None:
        self._session = session

    def say(
        self,
        content,
        *,
        audio: AsyncIterator[rtc.AudioFrame] | None = None,
        allow_interruptions: bool = True,
        add_to_chat_ctx: bool = True,
    ):
        if audio is None:
            return self._session.say(
                content,
                allow_interruptions=allow_interruptions,
                add_to_chat_ctx=add_to_chat_ctx,
            )

        return self._session.say(
            content,
            audio=audio,
            allow_interruptions=allow_interruptions,
            add_to_chat_ctx=add_to_chat_ctx,
        )

    def should_play_server_thinking_sound(self) -> bool:
        room = self._session.room_io.room
        return any(
            participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
            for participant in room.remote_participants.values()
        )

    async def publish_artifact(
        self, text: str, attributes: dict[str, str]
    ) -> None:
        await self._session.room_io.room.local_participant.send_text(
            text,
            topic=REPOLINE_UI_ARTIFACT_TOPIC,
            attributes=attributes,
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
        stt=_build_stt(),
        tts=_build_tts(),
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
    orchestrator = TurnOrchestrator(
        config=TurnOrchestratorConfig.from_bridge_config(SETTINGS),
        session=LiveKitTurnSession(session),
        telemetry=telemetry,
    )
    background_tasks: set[asyncio.Task[None]] = set()
    processed_chat_message_ids: set[str] = set()

    def track_background_task(task: asyncio.Task[None]) -> None:
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    async def handle_chat_text_stream(reader, participant_identity: str) -> None:
        if participant_identity == ctx.room.local_participant.identity:
            return

        try:
            text = await reader.read_all()
        except Exception:
            logger.exception("failed to read incoming chat text stream")
            return

        message_id = reader.info.stream_id
        if message_id in processed_chat_message_ids:
            return
        processed_chat_message_ids.add(message_id)

        telemetry.emit(
            "user_chat_stream_received",
            participant_identity=participant_identity,
            message_id=message_id,
            topic=reader.info.topic,
            attributes=reader.info.attributes,
            transcript=text,
        )
        await orchestrator.submit(
            TurnInput.chat_text(
                text,
                participant_identity=participant_identity,
                message_id=message_id,
            )
        )

    async def handle_legacy_chat_packet(packet) -> None:
        participant = packet.participant
        if packet.topic != LIVEKIT_LEGACY_CHAT_TOPIC or participant is None:
            return
        if participant.identity == ctx.room.local_participant.identity:
            return

        try:
            payload = json.loads(packet.data.decode("utf-8"))
        except Exception:
            logger.exception("failed to decode incoming legacy chat packet")
            return

        message_id = payload.get("id")
        if isinstance(message_id, str) and message_id in processed_chat_message_ids:
            return

        text = str(payload.get("message") or "").strip()
        if not text:
            return

        if isinstance(message_id, str):
            processed_chat_message_ids.add(message_id)

        telemetry.emit(
            "user_legacy_chat_received",
            participant_identity=participant.identity,
            message_id=message_id,
            topic=packet.topic,
            transcript=text,
        )
        await orchestrator.submit(
            TurnInput.legacy_chat(
                text,
                participant_identity=participant.identity,
                message_id=message_id if isinstance(message_id, str) else None,
            )
        )

    async def publish_runtime_state(
        *,
        request_id: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "type": "session_state",
            "state": orchestrator.runtime_state().to_payload(),
        }
        if request_id:
            payload["requestId"] = request_id

        await session.room_io.room.local_participant.send_text(
            json.dumps(payload),
            topic=REPOLINE_SESSION_STATE_TOPIC,
        )

    async def publish_control_result(
        *,
        action: str,
        ok: bool,
        message: str,
        request_id: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "type": "control_result",
            "action": action,
            "ok": ok,
            "message": message,
            "state": orchestrator.runtime_state().to_payload(),
        }
        if request_id:
            payload["requestId"] = request_id

        await session.room_io.room.local_participant.send_text(
            json.dumps(payload),
            topic=REPOLINE_SESSION_STATE_TOPIC,
        )

    async def handle_control_text_stream(reader, participant_identity: str) -> None:
        if participant_identity == ctx.room.local_participant.identity:
            return

        try:
            text = await reader.read_all()
        except Exception:
            logger.exception("failed to read incoming control text stream")
            return

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("ignoring invalid control payload: %s", text)
            return

        request_id = payload.get("requestId")
        if not isinstance(request_id, str):
            request_id = None

        control_type = str(payload.get("type") or "").strip()
        telemetry.emit(
            "runtime_control_received",
            participant_identity=participant_identity,
            control_type=control_type,
            request_id=request_id,
            payload=payload,
        )

        if control_type == "request_session_state":
            await publish_runtime_state(request_id=request_id)
            return

        if control_type != "set_model":
            await publish_control_result(
                action=control_type or "unknown",
                ok=False,
                message="Unsupported runtime control.",
                request_id=request_id,
            )
            return

        requested_model = payload.get("model")
        if requested_model is not None and not isinstance(requested_model, str):
            await publish_control_result(
                action="set_model",
                ok=False,
                message="Model must be a string.",
                request_id=request_id,
            )
            return

        try:
            state = orchestrator.set_runtime_model(requested_model)
        except ValueError as exc:
            await publish_control_result(
                action="set_model",
                ok=False,
                message=str(exc),
                request_id=request_id,
            )
            return

        await publish_control_result(
            action="set_model",
            ok=True,
            message=f"Runtime model updated to {state.active_model or 'the default model'}.",
            request_id=request_id,
        )

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
        track_background_task(asyncio.create_task(orchestrator.shutdown()))

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(transcript) -> None:
        track_background_task(
            asyncio.create_task(
                orchestrator.submit(
                    TurnInput.voice_transcript(
                        transcript.transcript,
                        is_final=transcript.is_final,
                    )
                )
            )
        )

    def on_chat_text_stream(reader, participant_identity: str) -> None:
        track_background_task(
            asyncio.create_task(handle_chat_text_stream(reader, participant_identity))
        )

    ctx.room.register_text_stream_handler(LIVEKIT_CHAT_TOPIC, on_chat_text_stream)

    def on_control_text_stream(reader, participant_identity: str) -> None:
        track_background_task(
            asyncio.create_task(handle_control_text_stream(reader, participant_identity))
        )

    ctx.room.register_text_stream_handler(REPOLINE_CONTROL_TOPIC, on_control_text_stream)

    @ctx.room.on("data_received")
    def on_data_received(packet) -> None:
        if packet.topic != LIVEKIT_LEGACY_CHAT_TOPIC:
            return

        track_background_task(asyncio.create_task(handle_legacy_chat_packet(packet)))

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
    await publish_runtime_state()

    greeting = session.say(render_call_greeting(SETTINGS), add_to_chat_ctx=False)
    await greeting.wait_for_playout()


if __name__ == "__main__":
    cli.run_app(SERVER)
