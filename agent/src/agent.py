from __future__ import annotations

import asyncio
import json
import logging
import os
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

from bridge_config import BridgeConfig
from telemetry import BridgeTelemetry
from turn_coordinator import TurnCoordinator, TurnCoordinatorConfig

logger = logging.getLogger("repoline-bridge")
REPOLINE_UI_ARTIFACT_TOPIC = "repoline.ui.artifact"
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


class LiveKitTurnSession:
    def __init__(self, session: AgentSession) -> None:
        self._session = session

    def say(
        self,
        content,
        *,
        allow_interruptions: bool = True,
        add_to_chat_ctx: bool = True,
    ):
        return self._session.say(
            content,
            allow_interruptions=allow_interruptions,
            add_to_chat_ctx=add_to_chat_ctx,
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
    coordinator = TurnCoordinator(
        config=TurnCoordinatorConfig.from_bridge_config(SETTINGS),
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
        await coordinator.submit_text_turn(
            text,
            source="chat_text",
            participant_identity=participant_identity,
            message_id=message_id,
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
        await coordinator.submit_text_turn(
            text,
            source="chat_legacy",
            participant_identity=participant.identity,
            message_id=message_id if isinstance(message_id, str) else None,
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
        track_background_task(asyncio.create_task(coordinator.shutdown()))

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(transcript) -> None:
        coordinator.on_user_input_transcribed(
            transcript.transcript,
            is_final=transcript.is_final,
        )

    def on_chat_text_stream(reader, participant_identity: str) -> None:
        track_background_task(
            asyncio.create_task(handle_chat_text_stream(reader, participant_identity))
        )

    ctx.room.register_text_stream_handler(LIVEKIT_CHAT_TOPIC, on_chat_text_stream)

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

    greeting = session.say(SETTINGS.greeting, add_to_chat_ctx=False)
    await greeting.wait_for_playout()


if __name__ == "__main__":
    cli.run_app(SERVER)
