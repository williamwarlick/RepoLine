from __future__ import annotations

import pytest

from cursor_app_submit import CursorAppSubmitResult
from provider_stream.common import TextStreamConfig
from provider_stream.cursor_app import (
    CursorAppTransport,
    _seed_bubbles_before_submitted_response,
)


class FakeSubmitter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.result = CursorAppSubmitResult(composer_id="composer-123")

    async def submit(
        self,
        *,
        workspace_root: str,
        prompt: str,
        command_title: str,
        submit_mode: str | None,
    ) -> CursorAppSubmitResult:
        self.calls.append(
            {
                "workspace_root": workspace_root,
                "prompt": prompt,
                "command_title": command_title,
                "submit_mode": submit_mode,
            }
        )
        return self.result


class FakeTail:
    def __init__(self, update_batches):
        self._update_batches = list(update_batches)
        self.seeded = []

    def seed_known_bubbles(self, bubbles) -> None:
        self.seeded.extend(bubbles)

    def snapshot_updates(self, *, include_existing: bool = False):
        if self._update_batches:
            return self._update_batches.pop(0)
        return []


def _assistant_update(text: str):
    class Bubble:
        def __init__(self) -> None:
            self.role = "assistant"
            self.is_tool_event = False
            self.raw: dict[str, str] = {}
            self.bubble_id = "bubble-123"
            self.request_id = "req-123"

    class Update:
        def __init__(self) -> None:
            self.kind = "new"
            self.bubble = Bubble()
            self.delta_text = text

    return Update()


def _assistant_bubble(text: str):
    class Bubble:
        def __init__(self) -> None:
            self.bubble_id = f"bubble-{text}"
            self.text = text
            self.role = "assistant"

    return Bubble()


def _user_bubble(text: str):
    class Bubble:
        def __init__(self) -> None:
            self.bubble_id = f"user-{abs(hash(text))}"
            self.text = text
            self.role = "user"

    return Bubble()


@pytest.mark.asyncio
async def test_cursor_app_transport_streams_assistant_text_and_completes() -> None:
    submitter = FakeSubmitter()
    statuses = iter(
        [
            {"status": "generating", "generatingBubbleIds": ["bubble-1"]},
            {"status": "completed", "generatingBubbleIds": []},
            {"status": "completed", "generatingBubbleIds": []},
        ]
    )

    transport = CursorAppTransport(
        submitter=submitter,
        composer_id_resolver=lambda workspace: "composer-123",
        tail_factory=lambda composer_id: FakeTail(
            [
                [],
                [_assistant_update("Fast reply.")],
                [],
            ]
        ),
        composer_loader=lambda composer_id: next(statuses),
        poll_interval_seconds=0,
        settle_delay_seconds=0,
        response_timeout_seconds=1,
    )

    events = [
        event
        async for event in transport.stream(
            TextStreamConfig(
                provider="cursor",
                provider_transport="app",
                provider_submit_mode="bridge-composer-handle",
                prompt="Say hi",
                working_directory="/tmp/demo",
                chunk_chars=8,
            )
        )
    ]

    assert [event.message for event in events if event.type == "status"] == [
        "Starting Cursor App stream.",
        "Cursor App submitted the turn.",
    ]
    assistant_deltas = [event for event in events if event.type == "assistant_delta"]
    assert assistant_deltas[0].text == "Fast reply."
    assert assistant_deltas[0].trace == {
        "composer_id": "composer-123",
        "bubble_id": "bubble-123",
        "request_id": "req-123",
        "kind": "new",
    }
    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "Fast reply."
    ]
    assert events[-1].type == "done"
    assert submitter.calls[0]["workspace_root"].endswith("/tmp/demo")
    assert submitter.calls[0]["prompt"].endswith("Say hi")
    assert submitter.calls[0]["submit_mode"] == "bridge-composer-handle"


@pytest.mark.asyncio
async def test_cursor_app_transport_adds_readonly_note_to_submitted_prompt() -> None:
    submitter = FakeSubmitter()

    transport = CursorAppTransport(
        submitter=submitter,
        composer_id_resolver=lambda workspace: "composer-123",
        tail_factory=lambda composer_id: FakeTail(
            [
                [],
                [_assistant_update("Readonly answer.")],
                [],
            ]
        ),
        composer_loader=lambda composer_id: {
            "status": "completed",
            "generatingBubbleIds": [],
        },
        poll_interval_seconds=0,
        settle_delay_seconds=0,
        response_timeout_seconds=1,
    )

    events = [
        event
        async for event in transport.stream(
            TextStreamConfig(
                provider="cursor",
                provider_transport="app",
                prompt="Say hi",
                access_policy="readonly",
                working_directory="/tmp/demo",
            )
        )
    ]

    assert any(event.type == "done" for event in events)
    assert "readonly" in submitter.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_cursor_app_transport_switches_to_submitted_composer_id() -> None:
    submitter = FakeSubmitter()
    submitter.result = CursorAppSubmitResult(composer_id="composer-live")
    created_tails: dict[str, FakeTail] = {}

    def make_tail(composer_id: str) -> FakeTail:
        tail = FakeTail([[], [_assistant_update(f"reply from {composer_id}")], []])
        created_tails[composer_id] = tail
        return tail

    transport = CursorAppTransport(
        submitter=submitter,
        composer_id_resolver=lambda workspace: "composer-stale",
        tail_factory=make_tail,
        bubble_loader=lambda composer_id: [_assistant_bubble(f"old-{composer_id}")],
        composer_loader=lambda composer_id: {
            "status": "completed",
            "generatingBubbleIds": [],
        },
        poll_interval_seconds=0,
        settle_delay_seconds=0,
        response_timeout_seconds=1,
    )

    events = [
        event
        async for event in transport.stream(
            TextStreamConfig(
                provider="cursor",
                provider_transport="app",
                prompt="Say hi",
                working_directory="/tmp/demo",
            )
        )
    ]

    assert [event.message for event in events if event.type == "status"] == [
        "Starting Cursor App stream.",
        "Cursor App submitted the turn.",
    ]
    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "reply from composer-live"
    ]
    assert [bubble.text for bubble in created_tails["composer-live"].seeded] == [
        "old-composer-live"
    ]
    assert events[-1].session_id == "composer-live"


@pytest.mark.asyncio
async def test_cursor_app_transport_does_not_replay_existing_history() -> None:
    submitter = FakeSubmitter()

    transport = CursorAppTransport(
        submitter=submitter,
        composer_id_resolver=lambda workspace: "composer-live",
        bubble_loader=lambda composer_id: [_assistant_bubble("old reply")],
        tail_factory=lambda composer_id: FakeTail(
            [[_assistant_update("new reply")], []]
        ),
        composer_loader=lambda composer_id: {
            "status": "completed",
            "generatingBubbleIds": [],
        },
        poll_interval_seconds=0,
        settle_delay_seconds=0,
        response_timeout_seconds=1,
    )

    events = [
        event
        async for event in transport.stream(
            TextStreamConfig(
                provider="cursor",
                provider_transport="app",
                prompt="Say hi",
                working_directory="/tmp/demo",
            )
        )
    ]

    assert [event.text for event in events if event.type == "speech_chunk"] == [
        "new reply"
    ]


def test_seed_bubbles_before_submitted_response_leaves_post_prompt_assistant_unseeded() -> None:
    bubbles = [
        _user_bubble("older prompt"),
        _assistant_bubble("older reply"),
        _user_bubble("submitted prompt"),
        _assistant_bubble("new reply"),
    ]

    seeded = _seed_bubbles_before_submitted_response(
        bubbles,
        prompt="submitted prompt",
    )

    assert [bubble.text for bubble in seeded] == [
        "older prompt",
        "older reply",
        "submitted prompt",
    ]
