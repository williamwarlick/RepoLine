from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from model_stream import TextStreamEvent
from turn_coordinator import TurnCoordinator, TurnCoordinatorConfig


class FakeTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event_type: str, **fields: object) -> None:
        self.events.append((event_type, fields))


class FakeSpeechHandle:
    def __init__(self, *, text: str | None = None) -> None:
        self.text = text
        self.chunks: list[str] = []
        self.interrupted = False
        self._done = asyncio.Event()
        self._consumer_task: asyncio.Task[None] | None = None

    def attach_consumer(self, task: asyncio.Task[None]) -> None:
        self._consumer_task = task
        task.add_done_callback(self._finish_from_task)

    def finish(self) -> None:
        self._done.set()

    def done(self) -> bool:
        return self._done.is_set()

    def interrupt(self, *, force: bool = False) -> None:
        self.interrupted = True
        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
        self._done.set()

    async def wait_for_playout(self) -> None:
        await self._done.wait()

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


def _config(**overrides: object) -> TurnCoordinatorConfig:
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
    return TurnCoordinatorConfig(**values)


@pytest.mark.asyncio
async def test_short_final_transcripts_merge_into_one_turn() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()
    started_prompts: list[str] = []

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        started_prompts.append(config.prompt)
        yield TextStreamEvent(type="speech_chunk", text="Working on it.", session_id="s1")
        yield TextStreamEvent(type="done", exit_code=0, session_id="s1")

    coordinator = TurnCoordinator(
        config=_config(),
        session=session,
        telemetry=telemetry,
        stream_events=stream_events,
    )

    coordinator.on_user_input_transcribed("Need", is_final=True)
    await asyncio.sleep(0.005)
    coordinator.on_user_input_transcribed("help", is_final=True)
    await asyncio.sleep(0.015)
    assert started_prompts == []

    await asyncio.sleep(0.04)
    await coordinator.shutdown()

    assert started_prompts == ["Need help"]
    assert any(event == "turn_merged" for event, _ in telemetry.events)
    assert session.stream_messages[0].chunks == ["Working on it."]


@pytest.mark.asyncio
async def test_partial_transcript_does_not_force_interrupt_active_speech() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()
    release_stream = asyncio.Event()

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        del config
        yield TextStreamEvent(type="speech_chunk", text="Working on it.", session_id="s1")
        await release_stream.wait()
        yield TextStreamEvent(type="done", exit_code=0, session_id="s1")

    coordinator = TurnCoordinator(
        config=_config(),
        session=session,
        telemetry=telemetry,
        stream_events=stream_events,
    )

    await coordinator.submit_text_turn("Please inspect the repo", source="chat_text")
    await asyncio.sleep(0.01)

    coordinator.on_user_input_transcribed("Wait", is_final=False)
    await asyncio.sleep(0.01)
    release_stream.set()
    await asyncio.sleep(0.01)

    assert len(session.stream_messages) == 1
    assert session.stream_messages[0].interrupted is False

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_final_interruption_replaces_active_speech_with_new_turn() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()
    started_prompts: list[str] = []
    release_first_turn = asyncio.Event()

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        started_prompts.append(config.prompt)
        yield TextStreamEvent(type="speech_chunk", text="Working on it.", session_id="s1")
        if len(started_prompts) == 1:
            await release_first_turn.wait()
        yield TextStreamEvent(type="done", exit_code=0, session_id="s1")

    coordinator = TurnCoordinator(
        config=_config(),
        session=session,
        telemetry=telemetry,
        stream_events=stream_events,
    )

    await coordinator.submit_text_turn("Please inspect the repo", source="chat_text")
    await asyncio.sleep(0.01)

    coordinator.on_user_input_transcribed("Wait", is_final=False)
    coordinator.on_user_input_transcribed("Do the README instead", is_final=True)
    await asyncio.sleep(0.05)
    release_first_turn.set()
    await asyncio.sleep(0.02)
    await coordinator.shutdown()

    assert started_prompts == ["Please inspect the repo", "Do the README instead"]
    assert len(session.stream_messages) == 2
    assert session.stream_messages[0].interrupted is True
    assert session.stream_messages[1].chunks == ["Working on it."]


@pytest.mark.asyncio
async def test_turn_coordinator_skips_bridge_status_for_fast_first_chunk() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        del config
        yield TextStreamEvent(type="speech_chunk", text="First chunk.", session_id="s1")
        yield TextStreamEvent(type="done", exit_code=0, session_id="s1")

    coordinator = TurnCoordinator(
        config=_config(),
        session=session,
        telemetry=telemetry,
        stream_events=stream_events,
    )

    await coordinator.submit_text_turn("Quick answer", source="chat_text")
    await asyncio.sleep(0.02)
    await coordinator.shutdown()

    assert session.string_messages == []
    assert not any(event.startswith("bridge_status") for event, _ in telemetry.events)
    assert session.stream_messages[0].chunks == ["First chunk."]
