from __future__ import annotations

import json

import pytest

from latency_harness import (
    BenchmarkScenario,
    CursorCommandAccumulator,
    ProviderCommandAccumulator,
    build_scenario_config,
    load_benchmark_plan,
    measure_provider_stream_turn,
)
from model_stream import TextStreamConfig, TextStreamEvent


def test_load_benchmark_plan_merges_defaults_and_resolves_workdir(tmp_path) -> None:
    plan_path = tmp_path / "bench.json"
    plan_path.write_text(
        json.dumps(
            {
                "defaults": {
                    "provider": "cursor",
                    "working_directory": ".",
                    "chunk_chars": 120,
                },
                "scenarios": [
                    {
                        "name": "stream",
                "kind": "provider_stream",
                        "prompt": "What does RepoLine do?",
                        "provider_submit_mode": "bridge-composer-handle",
                        "latency_archetype": "planning-question",
                        "prompt_variant": "current_baseline",
                        "prompt_id": "repo-summary-1",
                        "report_group": "core",
                    },
                    {
                        "name": "direct",
                        "kind": "cursor_command",
                        "turns": [
                            {"label": "first", "prompt": "Hello"},
                            {"label": "second", "prompt": "Follow up"},
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = load_benchmark_plan(plan_path, working_directory=tmp_path)

    assert len(plan.scenarios) == 2
    assert plan.scenarios[0].working_directory == str(tmp_path.resolve())
    assert plan.scenarios[0].chunk_chars == 120
    assert plan.scenarios[0].provider_submit_mode == "bridge-composer-handle"
    assert plan.scenarios[0].timeout_seconds == 60
    assert plan.scenarios[0].latency_archetype == "planning-question"
    assert plan.scenarios[0].prompt_variant == "current_baseline"
    assert plan.scenarios[0].prompt_id == "repo-summary-1"
    assert plan.scenarios[0].report_group == "core"
    assert [turn.label for turn in plan.scenarios[1].turns] == ["first", "second"]


def test_build_scenario_config_can_embed_repoline_prompt(tmp_path) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir(parents=True)
    (workdir / "README.md").write_text(
        "RepoLine is a voice bridge for coding agents.\n",
        encoding="utf-8",
    )
    installed_rule = workdir / ".cursor" / "rules" / "repoline-voice-session.mdc"
    installed_rule.parent.mkdir(parents=True)
    installed_rule.write_text(
        """---
description: RepoLine voice session behavior
alwaysApply: true
---
""",
        encoding="utf-8",
    )

    scenario = BenchmarkScenario(
        name="cursor-repoline",
        kind="cursor_command",
        provider="cursor",
        provider_submit_mode="bridge-composer-handle",
        working_directory=str(workdir),
        prompt="What does RepoLine do?",
        use_repoline_prompt=True,
        system_prompt="Speak plainly.",
    )

    config = build_scenario_config(scenario, prompt="What does RepoLine do?")

    assert config.system_prompt is not None
    assert config.system_prompt.startswith("Speak plainly.")
    assert config.provider_submit_mode == "bridge-composer-handle"
    assert "RepoLine voice session" in config.system_prompt
    assert "Answer directly from the request and obvious repo context when you can." in config.system_prompt


@pytest.mark.asyncio
async def test_measure_provider_stream_turn_tracks_first_chunk_and_done() -> None:
    async def fake_stream(_config: TextStreamConfig):
        yield TextStreamEvent(type="status", message="Starting Cursor Agent stream.")
        yield TextStreamEvent(type="assistant_delta", text="RepoLine is")
        yield TextStreamEvent(
            type="speech_chunk", text="RepoLine is live.", final=False
        )
        yield TextStreamEvent(type="done", exit_code=0, session_id="cursor-session")

    result = await measure_provider_stream_turn(
        TextStreamConfig(provider="cursor", prompt="Hello"),
        scenario_name="stream",
        repeat_index=1,
        turn_index=1,
        stream_events=fake_stream,
    )

    assert result.provider_first_status_message == "Starting Cursor Agent stream."
    assert result.provider_first_assistant_preview == "RepoLine is"
    assert result.spoken_response_preview == "RepoLine is live."
    assert result.response_text == "RepoLine is live."
    assert result.outcome == "ok"
    assert result.exit_code == 0
    assert result.session_id == "cursor-session"
    assert result.status_count == 1
    assert result.speech_chunk_count == 1


def test_cursor_command_accumulator_tracks_first_assistant_and_chunk() -> None:
    accumulator = CursorCommandAccumulator(provider="cursor", chunk_chars=140)
    accumulator.observe_line(
        json.dumps({"type": "system", "subtype": "init", "session_id": "cursor-1"}),
        elapsed_ms=12.0,
    )
    accumulator.observe_line(
        json.dumps(
            {
                "type": "assistant",
                "session_id": "cursor-1",
                "message": {"content": [{"type": "text", "text": "Looking now."}]},
            }
        ),
        elapsed_ms=55.0,
    )
    accumulator.observe_line(
        json.dumps(
            {
                "type": "assistant",
                "session_id": "cursor-1",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Looking now. RepoLine is a voice bridge.",
                        }
                    ]
                },
            }
        ),
        elapsed_ms=80.0,
    )
    accumulator.observe_line(
        json.dumps(
            {
                "type": "result",
                "session_id": "cursor-1",
                "result": "Looking now. RepoLine is a voice bridge.",
            }
        ),
        elapsed_ms=120.0,
    )

    assert accumulator.session_id == "cursor-1"
    assert accumulator.provider_first_status_ms == 12.0
    assert accumulator.provider_first_assistant_delta_ms == 55.0
    assert accumulator.provider_first_assistant_preview == "Looking now."
    assert accumulator.spoken_response_latency_ms == 55.0
    assert accumulator.spoken_response_preview == "Looking now."
    assert accumulator.response_text == "Looking now. RepoLine is a voice bridge."
    assert accumulator.speech_chunk_count == 2


def test_provider_command_accumulator_tracks_gemini_first_assistant_and_chunk() -> None:
    accumulator = ProviderCommandAccumulator(provider="gemini", chunk_chars=140)
    accumulator.observe_line(
        json.dumps(
            {
                "type": "init",
                "session_id": "gemini-1",
                "model": "gemini-2.5-flash",
            }
        ),
        elapsed_ms=10.0,
    )
    accumulator.observe_line(
        json.dumps(
            {
                "type": "message",
                "session_id": "gemini-1",
                "role": "assistant",
                "content": "Hi there!",
                "delta": True,
            }
        ),
        elapsed_ms=42.0,
    )
    accumulator.observe_line(
        json.dumps(
            {
                "type": "result",
                "session_id": "gemini-1",
                "status": "success",
            }
        ),
        elapsed_ms=55.0,
    )

    assert accumulator.session_id == "gemini-1"
    assert accumulator.provider_first_status_ms == 10.0
    assert accumulator.provider_first_status_message == "Gemini CLI started a session."
    assert accumulator.provider_first_assistant_delta_ms == 42.0
    assert accumulator.provider_first_assistant_preview == "Hi there!"
    assert accumulator.spoken_response_latency_ms == 42.0
    assert accumulator.spoken_response_preview == "Hi there!"
    assert accumulator.response_text == "Hi there!"
    assert accumulator.speech_chunk_count == 1


def test_provider_command_accumulator_tracks_openclaw_plain_output() -> None:
    accumulator = ProviderCommandAccumulator(provider="openclaw", chunk_chars=140)
    accumulator.observe_line(
        "[agent/embedded] embedded run start: runId=1 sessionId=openclaw-1",
        elapsed_ms=8.0,
    )
    accumulator.observe_line(
        "[agent/embedded] embedded run agent start: runId=1",
        elapsed_ms=14.0,
    )
    accumulator.observe_line(
        "Two plus two equals four.",
        elapsed_ms=1200.0,
    )

    assert accumulator.provider_first_status_ms == 8.0
    assert accumulator.provider_first_status_message == "OpenClaw started a session."
    assert accumulator.provider_first_assistant_delta_ms == 1200.0
    assert accumulator.provider_first_assistant_preview == "Two plus two equals four."
    assert accumulator.spoken_response_latency_ms == 1200.0
    assert accumulator.spoken_response_preview == "Two plus two equals four."


def test_provider_command_accumulator_tracks_openclaw_json_output() -> None:
    accumulator = ProviderCommandAccumulator(provider="openclaw", chunk_chars=140)
    accumulator.observe_line(
        json.dumps(
            {
                "payloads": [{"text": "RepoLine is a voice bridge."}],
                "meta": {
                    "agentMeta": {
                        "sessionId": "openclaw-2",
                    }
                },
            }
        ),
        elapsed_ms=2300.0,
    )

    assert accumulator.session_id == "openclaw-2"
    assert accumulator.provider_first_assistant_delta_ms == 2300.0
    assert accumulator.provider_first_assistant_preview == "RepoLine is a voice bridge."
    assert accumulator.spoken_response_latency_ms == 2300.0
    assert accumulator.spoken_response_preview == "RepoLine is a voice bridge."
