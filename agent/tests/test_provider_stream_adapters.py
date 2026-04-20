from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from model_stream import ProviderStreamFacade
from provider_stream.common import TextStreamConfig, TextStreamError, TextStreamEvent
from provider_stream.cursor import CursorProviderStreamAdapter
from provider_stream.gemini import GeminiProviderStreamAdapter


class FakeProcess:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self._lines = lines
        self.returncode = None
        self._final_returncode = returncode

    async def iter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def wait(self) -> int:
        self.returncode = self._final_returncode
        return self._final_returncode

    def terminate(self) -> None:
        self.returncode = self._final_returncode

    def kill(self) -> None:
        self.returncode = self._final_returncode


class FakeRunner:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.commands: list[list[str]] = []
        self.working_directories: list[str | None] = []

    async def spawn_jsonl(
        self, cmd: list[str], working_directory: str | None
    ) -> FakeProcess:
        self.commands.append(cmd)
        self.working_directories.append(working_directory)
        return self.process


async def _collect_events(
    events: AsyncIterator[TextStreamEvent],
) -> list[TextStreamEvent]:
    return [event async for event in events]


@pytest.mark.asyncio
async def test_claude_adapter_streams_partial_text_and_tool_artifacts() -> None:
    facade = ProviderStreamFacade()
    runner = FakeRunner(
        FakeProcess(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "toolu_1",
                                    "name": "exec_command",
                                    "input": {"command": ["pwd"]},
                                },
                                {"type": "text", "text": "I found it."},
                            ]
                        },
                    }
                ),
                json.dumps(
                    {"type": "stream_event", "event": {"type": "message_start"}}
                ),
                json.dumps(
                    {
                        "type": "stream_event",
                        "event": {
                            "type": "content_block_delta",
                            "delta": {"text": "Working on it. "},
                        },
                    }
                ),
                json.dumps({"type": "result", "is_error": False}),
            ]
        )
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="claude",
                prompt="Hello",
                session_id="claude-session",
                chunk_chars=8,
            ),
            runner=runner,
        )
    )

    assert events[0].type == "status"
    assert events[1].type == "artifact"
    assert events[1].artifact is not None
    assert events[1].artifact.title == "exec_command"
    assert events[2].message == "Claude Code accepted the turn."
    assert [event.text for event in events if event.type == "assistant_delta"] == [
        "Working on it. "
    ]
    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "Working on it."
    ]
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_codex_adapter_streams_deltas_and_item_artifacts() -> None:
    facade = ProviderStreamFacade()
    runner = FakeRunner(
        FakeProcess(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "exec-1",
                            "type": "exec_command",
                            "command": ["git", "status", "--short"],
                        },
                    }
                ),
                json.dumps({"type": "agent_message_delta", "delta": "I found it. "}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "assistant-1",
                            "type": "agent_message",
                            "text": "I found it. I am patching it now.",
                        },
                    }
                ),
                json.dumps({"type": "task_complete"}),
            ]
        )
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="codex",
                prompt="Hello",
                chunk_chars=8,
            ),
            runner=runner,
        )
    )

    assert [event.message for event in events if event.type == "status"] == [
        "Starting Codex CLI stream.",
        "Codex CLI started a session.",
        "Codex CLI accepted the turn.",
    ]
    assert [event.text for event in events if event.type == "assistant_delta"] == [
        "I found it. ",
        "I am patching it now.",
    ]
    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "I found it.",
        "I am patching it now.",
    ]
    artifacts = [event.artifact for event in events if event.type == "artifact"]
    assert artifacts[0] is not None
    assert artifacts[0].title == "Exec Command"
    assert artifacts[0].text == "git status --short"
    assert events[-1].type == "done"
    assert events[-1].session_id == "thread-123"


@pytest.mark.asyncio
async def test_cursor_adapter_ignores_replayed_full_text_updates() -> None:
    facade = ProviderStreamFacade()
    runner = FakeRunner(
        FakeProcess(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "cursor-session",
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "session_id": "cursor-session",
                        "message": {
                            "content": [{"type": "text", "text": "I found the issue."}]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "session_id": "cursor-session",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "I found the issue. I am patching it now.",
                                }
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "session_id": "cursor-session",
                        "result": "I found the issue. I am patching it now.",
                    }
                ),
            ]
        )
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="cursor",
                prompt="Hello",
                chunk_chars=8,
            ),
            runner=runner,
        )
    )

    assert [event.text for event in events if event.type == "assistant_delta"] == [
        "I found the issue.",
        " I am patching it now.",
    ]
    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "I found the issue.",
        "I am patching it now.",
    ]
    assert events[-1].type == "done"
    assert events[-1].session_id == "cursor-session"


@pytest.mark.asyncio
async def test_cursor_adapter_uses_app_transport_when_requested() -> None:
    class FakeCursorAppTransport:
        async def stream(
            self, config: TextStreamConfig
        ) -> AsyncIterator[TextStreamEvent]:
            yield TextStreamEvent(type="status", message="app")
            yield TextStreamEvent(type="done", session_id="composer-123")

    facade = ProviderStreamFacade(
        adapters={
            "cursor": CursorProviderStreamAdapter(
                app_transport=FakeCursorAppTransport()
            ),
        }
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="cursor",
                provider_transport="app",
                prompt="Hello",
            ),
            runner=FakeRunner(FakeProcess([])),
        )
    )

    assert [event.message for event in events if event.type == "status"] == ["app"]
    assert events[-1].session_id == "composer-123"


@pytest.mark.asyncio
async def test_cursor_adapter_surfaces_app_transport_error_when_requested() -> None:
    class FakeFailingCursorAppTransport:
        async def stream(
            self, config: TextStreamConfig
        ) -> AsyncIterator[TextStreamEvent]:
            yield TextStreamEvent(type="status", message="Starting Cursor App stream.")
            raise TextStreamError("Cursor app submit failed.")

    facade = ProviderStreamFacade(
        adapters={
            "cursor": CursorProviderStreamAdapter(
                app_transport=FakeFailingCursorAppTransport()
            ),
        }
    )
    with pytest.raises(TextStreamError, match=r"Cursor app submit failed\."):
        await _collect_events(
            facade.events(
                TextStreamConfig(
                    provider="cursor",
                    provider_transport="app",
                    prompt="Hello",
                ),
                runner=FakeRunner(FakeProcess([])),
            )
        )


@pytest.mark.asyncio
async def test_cursor_adapter_streams_partial_output_fragments_without_duplication() -> (
    None
):
    facade = ProviderStreamFacade()
    runner = FakeRunner(
        FakeProcess(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "cursor-session",
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "session_id": "cursor-session",
                        "message": {"content": [{"type": "text", "text": "Hello"}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "session_id": "cursor-session",
                        "message": {"content": [{"type": "text", "text": " world."}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "session_id": "cursor-session",
                        "message": {
                            "content": [{"type": "text", "text": "Hello world."}]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "session_id": "cursor-session",
                        "result": "Hello world.",
                    }
                ),
            ]
        )
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="cursor",
                prompt="Hello",
                chunk_chars=100,
            ),
            runner=runner,
        )
    )

    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "Hello world."
    ]
    assert [event.text for event in events if event.type == "assistant_delta"] == [
        "Hello",
        " world.",
    ]
    assert runner.commands[0].count("--stream-partial-output") == 1
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_cursor_adapter_reports_result_errors() -> None:
    facade = ProviderStreamFacade()
    runner = FakeRunner(
        FakeProcess(
            [
                json.dumps(
                    {
                        "type": "result",
                        "session_id": "cursor-session",
                        "is_error": True,
                        "result": "Authentication required",
                    }
                )
            ],
            returncode=1,
        )
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="cursor",
                prompt="Hello",
            ),
            runner=runner,
        )
    )

    error_events = [event for event in events if event.type == "error"]
    assert len(error_events) == 1
    assert error_events[0].message == "Authentication required"


@pytest.mark.asyncio
async def test_gemini_adapter_streams_deltas_and_tool_artifacts() -> None:
    facade = ProviderStreamFacade()
    runner = FakeRunner(
        FakeProcess(
            [
                json.dumps(
                    {
                        "type": "init",
                        "session_id": "gemini-session",
                        "model": "gemini-2.5-flash",
                    }
                ),
                json.dumps(
                    {
                        "type": "tool_use",
                        "tool_name": "read_file",
                        "tool_id": "tool-1",
                        "parameters": {"path": "README.md"},
                    }
                ),
                json.dumps(
                    {
                        "type": "message",
                        "role": "assistant",
                        "session_id": "gemini-session",
                        "content": "RepoLine connects voice calls to local coding CLIs.",
                        "delta": True,
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "session_id": "gemini-session",
                        "status": "success",
                    }
                ),
            ]
        )
    )

    events = await _collect_events(
        facade.events(
            TextStreamConfig(
                provider="gemini",
                prompt="Hello",
                chunk_chars=20,
            ),
            runner=runner,
        )
    )

    assert [event.message for event in events if event.type == "status"] == [
        "Starting Gemini CLI stream.",
        "Gemini CLI started a session.",
    ]
    assert [event.text for event in events if event.type == "assistant_delta"] == [
        "RepoLine connects voice calls to local coding CLIs."
    ]
    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "RepoLine connects voice calls to local coding CLIs."
    ]
    artifacts = [event.artifact for event in events if event.type == "artifact"]
    assert artifacts[0] is not None
    assert artifacts[0].title == "read_file"
    assert artifacts[0].text == '{\n  "path": "README.md"\n}'
    assert events[-1].type == "done"
    assert runner.commands[0][0] == "gemini"


@pytest.mark.asyncio
async def test_stream_text_chunks_raises_when_provider_finishes_without_text() -> None:
    facade = ProviderStreamFacade()
    runner = FakeRunner(FakeProcess([json.dumps({"type": "task_complete"})]))
    config = TextStreamConfig(provider="codex", prompt="Hello")

    with pytest.raises(TextStreamError, match="finished without producing speech text"):
        async for _ in facade.chunks(config, runner=runner):
            pass
