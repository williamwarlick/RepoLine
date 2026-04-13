from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

from model_stream import DEFAULT_PROVIDER_STREAM_FACADE, ProviderStreamFacade
from telemetry import BridgeTelemetry
from turn_coordinator import (
    MonotonicFn,
    SleepFn,
    TurnCoordinator,
    TurnCoordinatorConfig,
    TurnSession,
)

TurnOrchestratorConfig = TurnCoordinatorConfig
TurnInputSource = Literal["voice_transcript", "chat_text", "chat_legacy"]


@dataclass(frozen=True, slots=True)
class TurnInput:
    text: str
    source: TurnInputSource
    is_final: bool = True
    participant_identity: str | None = None
    message_id: str | None = None

    @classmethod
    def voice_transcript(cls, text: str, *, is_final: bool) -> "TurnInput":
        return cls(text=text, source="voice_transcript", is_final=is_final)

    @classmethod
    def chat_text(
        cls,
        text: str,
        *,
        participant_identity: str | None = None,
        message_id: str | None = None,
    ) -> "TurnInput":
        return cls(
            text=text,
            source="chat_text",
            participant_identity=participant_identity,
            message_id=message_id,
        )

    @classmethod
    def legacy_chat(
        cls,
        text: str,
        *,
        participant_identity: str | None = None,
        message_id: str | None = None,
    ) -> "TurnInput":
        return cls(
            text=text,
            source="chat_legacy",
            participant_identity=participant_identity,
            message_id=message_id,
        )


class TurnOrchestrator:
    def __init__(
        self,
        *,
        config: TurnOrchestratorConfig,
        session: TurnSession,
        telemetry: BridgeTelemetry,
        provider_stream: ProviderStreamFacade = DEFAULT_PROVIDER_STREAM_FACADE,
        sleep: SleepFn = asyncio.sleep,
        monotonic: MonotonicFn = time.monotonic,
    ) -> None:
        self._coordinator = TurnCoordinator(
            config=config,
            session=session,
            telemetry=telemetry,
            stream_events=provider_stream.events,
            sleep=sleep,
            monotonic=monotonic,
        )

    async def submit(self, turn_input: TurnInput) -> None:
        if turn_input.source == "voice_transcript":
            self._coordinator.on_user_input_transcribed(
                turn_input.text, is_final=turn_input.is_final
            )
            return

        await self._coordinator.submit_text_turn(
            turn_input.text,
            source=turn_input.source,
            participant_identity=turn_input.participant_identity,
            message_id=turn_input.message_id,
        )

    async def shutdown(self) -> None:
        await self._coordinator.shutdown()
