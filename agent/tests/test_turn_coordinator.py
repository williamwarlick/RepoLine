from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

import turn_coordinator as turn_coordinator_module
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
    def __init__(self, *, should_play_server_thinking_sound: bool = False) -> None:
        self.string_messages: list[FakeSpeechHandle] = []
        self.stream_messages: list[FakeSpeechHandle] = []
        self.audio_messages: list[FakeSpeechHandle] = []
        self.artifacts: list[tuple[str, dict[str, str]]] = []
        self.should_play_server_thinking_sound_value = should_play_server_thinking_sound

    def say(
        self,
        content: str | AsyncIterator[str],
        *,
        audio=None,
        allow_interruptions: bool = True,
        add_to_chat_ctx: bool = True,
    ) -> FakeSpeechHandle:
        del allow_interruptions, add_to_chat_ctx

        if audio is not None:
            handle = FakeSpeechHandle(text=content if isinstance(content, str) else None)
            task = asyncio.create_task(self._consume_audio(audio, handle))
            handle.attach_consumer(task)
            self.audio_messages.append(handle)
            return handle

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

    def should_play_server_thinking_sound(self) -> bool:
        return self.should_play_server_thinking_sound_value

    async def _consume_stream(
        self, content: AsyncIterator[str], handle: FakeSpeechHandle
    ) -> None:
        async for chunk in content:
            handle.chunks.append(chunk)

    async def _consume_audio(self, content, handle: FakeSpeechHandle) -> None:
        async for _ in content:
            handle.chunks.append("audio")
            await asyncio.sleep(0.001)


def _config(**overrides: object) -> TurnCoordinatorConfig:
    values: dict[str, object] = {
        "provider": "claude",
        "provider_transport": None,
        "provider_submit_mode": None,
        "chunk_chars": 8,
        "model": None,
        "thinking_level": "low",
        "system_prompt": "Speak briefly.",
        "working_directory": "/tmp/project",
        "access_policy": "readonly",
        "final_transcript_debounce_seconds": 0.01,
        "short_transcript_word_threshold": 2,
        "short_transcript_debounce_seconds": 0.03,
        "thinking_sound_preset": "soft-pulse",
        "thinking_sound_interval_ms": 1800,
        "thinking_sound_volume": 0.11,
        "thinking_sound_sip_only": True,
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
    session = FakeSession(should_play_server_thinking_sound=False)
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
    assert session.audio_messages == []
    assert not any(event.startswith("bridge_status") for event, _ in telemetry.events)
    assert session.stream_messages[0].chunks == ["First chunk."]


@pytest.mark.asyncio
async def test_turn_coordinator_starts_and_stops_server_thinking_sound_for_phone_turns() -> None:
    session = FakeSession(should_play_server_thinking_sound=True)
    telemetry = FakeTelemetry()
    release_stream = asyncio.Event()

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        del config
        await asyncio.sleep(0.02)
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

    assert len(session.audio_messages) == 1
    assert session.audio_messages[0].done() is False

    await asyncio.sleep(0.03)
    release_stream.set()
    await asyncio.sleep(0.02)
    await coordinator.shutdown()

    assert session.audio_messages[0].interrupted is True
    assert session.stream_messages[0].chunks == ["Working on it."]
    assert any(event == "thinking_sound_started" for event, _ in telemetry.events)
    assert any(event == "thinking_sound_stopped" for event, _ in telemetry.events)


def test_turn_coordinator_runtime_state_exposes_cursor_cli_model_controls() -> None:
    coordinator = TurnCoordinator(
        config=_config(
            provider="cursor",
            provider_transport="cli",
            model="composer-2-fast",
        ),
        session=FakeSession(),
        telemetry=FakeTelemetry(),
    )

    state = coordinator.runtime_state()

    assert state.provider == "cursor"
    assert state.provider_transport == "cli"
    assert state.active_model == "composer-2-fast"
    assert state.can_update_model is True
    assert state.model_options == ("composer-2-fast", "composer-2")


@pytest.mark.asyncio
async def test_turn_coordinator_applies_runtime_model_override_to_new_turns() -> None:
    session = FakeSession()
    telemetry = FakeTelemetry()
    seen_models: list[str | None] = []

    async def stream_events(config) -> AsyncIterator[TextStreamEvent]:
        seen_models.append(config.model)
        yield TextStreamEvent(type="speech_chunk", text="On it.", session_id="cursor-1")
        yield TextStreamEvent(type="done", exit_code=0, session_id="cursor-1")

    coordinator = TurnCoordinator(
        config=_config(
            provider="cursor",
            provider_transport="cli",
            model="composer-2-fast",
        ),
        session=session,
        telemetry=telemetry,
        stream_events=stream_events,
    )

    state = coordinator.set_runtime_model("composer-2")
    await coordinator.submit_text_turn("Summarize the repo", source="chat_text")
    await asyncio.sleep(0.02)
    await coordinator.shutdown()

    assert state.active_model == "composer-2"
    assert seen_models == ["composer-2"]


def test_turn_coordinator_updates_runtime_model_for_cursor_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated: list[tuple[str, str]] = []

    def fake_update_cursor_runtime_model(workspace_root: str, *, model: str) -> list[str]:
        updated.append((workspace_root, model))
        return ["composer-123"]

    monkeypatch.setattr(
        turn_coordinator_module,
        "update_cursor_runtime_model",
        fake_update_cursor_runtime_model,
    )

    coordinator = TurnCoordinator(
        config=_config(
            provider="cursor",
            provider_transport="app",
            model="composer-2-fast",
        ),
        session=FakeSession(),
        telemetry=FakeTelemetry(),
    )

    state = coordinator.set_runtime_model("composer-2")

    assert state.active_model == "composer-2"
    assert updated == [("/tmp/project", "composer-2")]


def test_turn_coordinator_runtime_state_uses_preferred_cursor_app_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        turn_coordinator_module,
        "resolve_runtime_composer_id",
        lambda workspace_root: "composer-live",
    )
    monkeypatch.setattr(
        turn_coordinator_module,
        "load_composer_data",
        lambda composer_id: {
            "modelConfig": {
                "modelName": "composer-2",
                "maxMode": False,
                "selectedModels": [
                    {
                        "modelId": "composer-2",
                        "parameters": [{"id": "fast", "value": "false"}],
                    }
                ],
            }
        },
    )

    coordinator = TurnCoordinator(
        config=_config(
            provider="cursor",
            provider_transport="app",
            model="composer-2-fast",
        ),
        session=FakeSession(),
        telemetry=FakeTelemetry(),
    )

    state = coordinator.runtime_state()

    assert state.active_model == "composer-2"
    assert state.can_update_model is True
