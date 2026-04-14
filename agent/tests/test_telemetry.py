import json

from telemetry import BridgeTelemetry


def test_bridge_telemetry_writes_jsonl(tmp_path) -> None:
    output_path = tmp_path / "bridge.jsonl"
    telemetry = BridgeTelemetry(str(output_path))

    telemetry.emit("turn_opened", turn_id="turn-123", transcript="hello")

    records = output_path.read_text(encoding="utf-8").strip().splitlines()

    assert len(records) == 1
    payload = json.loads(records[0])
    assert payload["event"] == "turn_opened"
    assert payload["turn_id"] == "turn-123"
    assert payload["transcript"] == "hello"


def test_bridge_telemetry_writes_latest_call_summary(tmp_path) -> None:
    output_path = tmp_path / "bridge.jsonl"
    telemetry = BridgeTelemetry(str(output_path))

    telemetry.emit(
        "bridge_session_started",
        room="call-room",
        provider="codex",
        workdir="/tmp/repo",
    )
    telemetry.emit("turn_opened", turn_id="turn-123", transcript="hello")
    telemetry.emit(
        "turn_merged",
        turn_id="turn-123",
        transcript="hello there",
        debounce_seconds=2.75,
    )
    telemetry.emit("model_turn_started", turn_id="turn-123")
    telemetry.emit(
        "model_status",
        turn_id="turn-123",
        message="Starting Codex CLI stream.",
        latency_ms=12.3,
    )
    telemetry.emit("model_first_chunk_ready", turn_id="turn-123", latency_ms=1234.5)
    telemetry.emit("model_speech_chunk", turn_id="turn-123", text="Hello there.")
    telemetry.emit("tts_playout_started", turn_id="turn-123")
    telemetry.emit("tts_playout_finished", turn_id="turn-123", latency_ms=2001.0)
    telemetry.emit(
        "model_turn_finished",
        turn_id="turn-123",
        completed=True,
        saw_text=True,
        latency_ms=2345.6,
        error_message=None,
    )
    telemetry.emit(
        "livekit_session_closed", reason="participant_disconnected", error=None
    )

    latest_summary = (tmp_path / "latest-call.md").read_text(encoding="utf-8")
    assert "Status: Ended" in latest_summary
    assert "Provider: codex" in latest_summary
    assert "User: hello" in latest_summary
    assert "Agent:" in latest_summary
    assert "Hello there." in latest_summary
    assert "First Spoken Chunk: 1234.5 ms" in latest_summary
    assert "Close Reason: participant_disconnected" in latest_summary
    assert "Latency Trail:" in latest_summary
    assert "Transcript merged" in latest_summary
    assert "First model status 12.3 ms after model start" in latest_summary
    assert "Speech playout finished 2001.0 ms after model start" in latest_summary

    history_files = list((tmp_path / "calls").glob("*.md"))
    assert len(history_files) == 1
