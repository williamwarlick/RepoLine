from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from model_stream import TextStreamEvent
from turn_orchestrator import TurnInput, TurnOrchestrator, TurnOrchestratorConfig


class FakeTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event_type: str, **fields: object) -> None:
        self.events.append((event_type, fields))


class FakeSpeechHandle:
    def __init__(self, *, text: str | None = None) -> None:
        self.text = text
        self.chunks: list[str] = []
        self._done = asyncio.Event()
        self._consumer_task: asyncio.Task[None] | None = None

    def attach_consumer(self, task: asyncio.Task[None]) -> None:
        self._consumer_task = task
        task.add_done_callback(self._finish_from_task)

    def done(self) -> bool:
        return self._done.is_set()

    def interrupt(self, *, force: bool = False) -> None:
        del force
        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
        self._done.set()

    async def wait_for_playout(self) -> None:
        await self._done.wait()

    def finish(self) -> None:
        self._done.set()

    def _finish_from_task(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            self._done.set()
            return
        task.result()
        self._done.set()


class FakeSession:
    def __init__(self) -> None:
        self.string_messages: list[FakeSpeechHandle] = []
        self.stream_messages: list[FakeSpeechHandle] = []
        self.artifacts: list[tuple[str, dict[str, str]]] = []

    def say(
        self,
        content: str | AsyncIterator[str],
        *,
        allow_interruptions: bool = True,
        add_to_chat_ctx: bool = True,
    ) -> FakeSpeechHandle:
        del allow_interruptions, add_to_chat_ctx

        if isinstance(content, str):
            handle = FakeSpeechHandle(text=content)
            handle.finish()
            self.string_messages.append(handle)
            return handle

        handle = FakeSpeechHandle()
        task = asyncio.create_task(self._consume_stream(content, handle))
        handle.attach_consumer(task)
        self.stream_messages.append(handle)
        return handle

    async def publish_artifact(self, text: str, attributes: dict[str, str]) -> None:
        self.artifacts.append((text, attributes))

    async def _consume_stream(
        self, content: AsyncIterator[str], handle: FakeSpeechHandle
    ) -> None:
        async for chunk in content:
            handle.chunks.append(chunk)


class FakeProviderStream:
    def __init__(self, stream_events) -> None:
        self._stream_events = stream_events

    async def events(self, config) -> AsyncIterator[TextStreamEvent]:
        async for event in self._stream_events(config):
            yield event


def _config(**overrides: object) -> TurnOrchestratorConfig:
    values: dict[str, object] = {
        "provider": "claude",
        "provider_transport": None,
        "chunk_chars": 8,
        "model": None,
        "thinking_level": "low",
        "system_prompt": "Speak briefly.",
        "working_directory": "/tmp/project",
        "access_policy": "readonly",
        "final_transcript_debounce_seconds": 0.01,
        "short_transcript_word_threshold": 2,
        "short_transcript_debounce_seconds": 0.03,
    }
    values.update(overrides)
    return TurnOrchestratorConfig(**values)


@pytest.mark.asyncio
async def test_turn_orchestrator_merges_voice_transcripts_before_starting_a_turn() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()
    started_prompts: list[str] = []

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        started_prompts.append(config.prompt)
        yield TextStreamEvent(type="speech_chunk", text="Working on it.", session_id="s1")
        yield TextStreamEvent(type="done", exit_code=0, session_id="s1")

    orchestrator = TurnOrchestrator(
        config=_config(),
        session=session,
        telemetry=telemetry,
        provider_stream=FakeProviderStream(stream_events),
    )

    await orchestrator.submit(TurnInput.voice_transcript("Need", is_final=True))
    await asyncio.sleep(0.005)
    await orchestrator.submit(TurnInput.voice_transcript("help", is_final=True))
    await asyncio.sleep(0.06)
    await orchestrator.shutdown()

    assert started_prompts == ["Need help"]
    assert any(event == "turn_merged" for event, _ in telemetry.events)
    assert session.stream_messages[0].chunks == ["Working on it."]


@pytest.mark.asyncio
async def test_turn_orchestrator_routes_chat_turns_with_metadata() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()
    started_prompts: list[str] = []

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        started_prompts.append(config.prompt)
        yield TextStreamEvent(type="speech_chunk", text="On it.", session_id="chat-1")
        yield TextStreamEvent(type="done", exit_code=0, session_id="chat-1")

    orchestrator = TurnOrchestrator(
        config=_config(),
        session=session,
        telemetry=telemetry,
        provider_stream=FakeProviderStream(stream_events),
    )

    await orchestrator.submit(
        TurnInput.chat_text(
            "Please inspect the repo",
            participant_identity="alice",
            message_id="msg-123",
        )
    )
    await asyncio.sleep(0.02)
    await orchestrator.shutdown()

    assert started_prompts == ["Please inspect the repo"]
    assert session.stream_messages[0].chunks == ["On it."]
    user_input_event = next(
        fields for event, fields in telemetry.events if event == "user_input_received"
    )
    assert user_input_event["transcript"] == "Please inspect the repo"
    assert user_input_event["input_source"] == "chat_text"
    assert user_input_event["participant_identity"] == "alice"
    assert user_input_event["message_id"] == "msg-123"
