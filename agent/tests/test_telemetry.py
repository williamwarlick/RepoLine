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
