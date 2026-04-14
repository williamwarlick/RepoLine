from __future__ import annotations

import dataclasses
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("repoline-bridge")


class BridgeTelemetry:
    def __init__(self, output_path: str | None = None) -> None:
        self._output_path = Path(output_path).expanduser() if output_path else None
        if self._output_path is not None:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            self._latest_summary_path = self._output_path.parent / "latest-call.md"
            self._history_dir = self._output_path.parent / "calls"
            self._history_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._latest_summary_path = None
            self._history_dir = None
        self._session = _SessionSummary()

    def emit(self, event_type: str, **fields: Any) -> None:
        record = {
            "timestamp": round(time.time(), 3),
            "event": event_type,
            **{key: _serialize(value) for key, value in fields.items()},
        }

        logger.info("bridge telemetry %s", event_type, extra={"bridge_event": record})

        if self._output_path is None:
            return

        try:
            with self._output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True))
                handle.write("\n")
        except Exception:
            logger.exception(
                "Failed to persist bridge telemetry",
                extra={"path": str(self._output_path)},
            )

        self._update_session_summary(record)

    def _update_session_summary(self, record: dict[str, Any]) -> None:
        event_type = record["event"]
        timestamp = float(record["timestamp"])

        if event_type == "bridge_session_started":
            self._session = _SessionSummary(
                started_at=timestamp,
                room=_string_value(record.get("room")),
                provider=_string_value(record.get("provider")),
                model=_string_value(record.get("model")),
                workdir=_string_value(record.get("workdir")),
                livekit_url=_string_value(record.get("livekit_url")),
                stt_model=_string_value(record.get("stt_model")),
                tts_model=_string_value(record.get("tts_model")),
            )

        turn = None
        turn_id = _string_value(record.get("turn_id"))
        if turn_id:
            turn = self._session.turns.setdefault(
                turn_id,
                _TurnSummary(turn_id=turn_id, opened_at=timestamp),
            )
            if turn_id not in self._session.turn_order:
                self._session.turn_order.append(turn_id)

        if event_type == "turn_opened" and turn is not None:
            turn.opened_at = timestamp
            turn.user_text = _string_value(record.get("transcript")) or turn.user_text
        elif event_type == "turn_merged" and turn is not None:
            turn.merged_at = timestamp
            turn.merged_debounce_seconds = _float_value(record.get("debounce_seconds"))
            turn.merged_text = (
                _string_value(record.get("transcript")) or turn.merged_text
            )
        elif event_type == "model_turn_started" and turn is not None:
            turn.model_started_at = timestamp
        elif event_type == "bridge_status_started" and turn is not None:
            _append_unique(turn.status_updates, _string_value(record.get("message")))
        elif event_type == "bridge_status_followup_started" and turn is not None:
            _append_unique(turn.followup_updates, _string_value(record.get("message")))
        elif event_type == "model_status" and turn is not None:
            _append_unique(turn.status_updates, _string_value(record.get("message")))
            if turn.first_status_latency_ms is None:
                turn.first_status_at = timestamp
                turn.first_status_latency_ms = _float_value(record.get("latency_ms"))
        elif event_type == "model_first_chunk_ready" and turn is not None:
            turn.first_chunk_latency_ms = _float_value(record.get("latency_ms"))
            if turn.first_chunk_at is None:
                turn.first_chunk_at = timestamp
        elif event_type == "model_speech_chunk" and turn is not None:
            _append_unique(turn.agent_chunks, _string_value(record.get("text")))
        elif event_type == "tts_playout_started" and turn is not None:
            turn.tts_started_at = timestamp
        elif event_type == "tts_playout_finished" and turn is not None:
            turn.tts_finished_at = timestamp
            turn.tts_finished_latency_ms = _float_value(record.get("latency_ms"))
        elif event_type == "model_turn_finished" and turn is not None:
            turn.completed = bool(record.get("completed"))
            turn.saw_text = bool(record.get("saw_text"))
            turn.total_latency_ms = _float_value(record.get("latency_ms"))
            turn.error_message = _string_value(record.get("error_message"))
        elif event_type == "livekit_session_closed":
            self._session.closed_at = timestamp
            self._session.close_reason = _string_value(record.get("reason"))
            self._session.close_error = _string_value(record.get("error"))

        self._write_latest_summary()
        if event_type == "livekit_session_closed":
            self._write_history_summary()

    def _write_latest_summary(self) -> None:
        if self._latest_summary_path is None:
            return

        try:
            self._latest_summary_path.write_text(
                _render_session_summary(self._session),
                encoding="utf-8",
            )
        except Exception:
            logger.exception(
                "Failed to persist latest call summary",
                extra={"path": str(self._latest_summary_path)},
            )

    def _write_history_summary(self) -> None:
        if self._history_dir is None or self._session.started_at is None:
            return

        timestamp = datetime.fromtimestamp(self._session.started_at).strftime(
            "%Y%m%d-%H%M%S"
        )
        room = _slugify(self._session.room or "session")
        path = self._history_dir / f"{timestamp}-{room}.md"
        try:
            path.write_text(_render_session_summary(self._session), encoding="utf-8")
        except Exception:
            logger.exception(
                "Failed to persist call history summary", extra={"path": str(path)}
            )


@dataclass(slots=True)
class _TurnSummary:
    turn_id: str
    opened_at: float | None = None
    merged_at: float | None = None
    merged_debounce_seconds: float | None = None
    model_started_at: float | None = None
    first_status_at: float | None = None
    first_status_latency_ms: float | None = None
    user_text: str | None = None
    merged_text: str | None = None
    status_updates: list[str] = field(default_factory=list)
    followup_updates: list[str] = field(default_factory=list)
    agent_chunks: list[str] = field(default_factory=list)
    first_chunk_latency_ms: float | None = None
    first_chunk_at: float | None = None
    tts_started_at: float | None = None
    tts_finished_at: float | None = None
    tts_finished_latency_ms: float | None = None
    total_latency_ms: float | None = None
    completed: bool | None = None
    saw_text: bool | None = None
    error_message: str | None = None


@dataclass(slots=True)
class _SessionSummary:
    started_at: float | None = None
    closed_at: float | None = None
    room: str | None = None
    provider: str | None = None
    model: str | None = None
    workdir: str | None = None
    livekit_url: str | None = None
    stt_model: str | None = None
    tts_model: str | None = None
    close_reason: str | None = None
    close_error: str | None = None
    turns: dict[str, _TurnSummary] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)


def _render_session_summary(session: _SessionSummary) -> str:
    lines = ["# RepoLine Call Summary", ""]

    status = "Ended" if session.closed_at is not None else "Active"
    lines.append(f"Status: {status}")
    if session.started_at is not None:
        lines.append(f"Started: {_format_timestamp(session.started_at)}")
    if session.closed_at is not None:
        lines.append(f"Ended: {_format_timestamp(session.closed_at)}")
    if session.close_reason:
        lines.append(f"Close Reason: {session.close_reason}")
    if session.close_error:
        lines.append(f"Close Error: {session.close_error}")
    if session.provider:
        lines.append(f"Provider: {session.provider}")
    if session.model:
        lines.append(f"Model: {session.model}")
    if session.room:
        lines.append(f"Room: {session.room}")
    if session.workdir:
        lines.append(f"Workdir: {session.workdir}")
    if session.livekit_url:
        lines.append(f"LiveKit URL: {session.livekit_url}")
    if session.stt_model:
        lines.append(f"STT: {session.stt_model}")
    if session.tts_model:
        lines.append(f"TTS: {session.tts_model}")
    lines.append("")

    if not session.turn_order:
        lines.append("No turns captured yet.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Turns")
    lines.append("")
    for index, turn_id in enumerate(session.turn_order, start=1):
        turn = session.turns[turn_id]
        lines.append(f"### Turn {index}")
        if turn.user_text:
            lines.append(f"User: {turn.user_text}")
        if turn.merged_text and turn.merged_text != turn.user_text:
            lines.append(f"Merged Transcript: {turn.merged_text}")
        if turn.status_updates:
            lines.append(f"Initial Status: {turn.status_updates[-1]}")
        if turn.followup_updates:
            lines.append(f"Followup Statuses: {' | '.join(turn.followup_updates)}")
        if turn.first_chunk_latency_ms is not None:
            lines.append(f"First Spoken Chunk: {turn.first_chunk_latency_ms:.1f} ms")
        if turn.total_latency_ms is not None:
            lines.append(f"Turn Finished: {turn.total_latency_ms:.1f} ms")
        if turn.completed is not None:
            lines.append(f"Completed: {'yes' if turn.completed else 'no'}")
        if turn.error_message:
            lines.append(f"Error: {turn.error_message}")
        latency_trail = _render_latency_trail(turn)
        if latency_trail:
            lines.append("Latency Trail:")
            lines.extend(latency_trail)
        agent_text = _join_chunks(turn.agent_chunks)
        if agent_text:
            lines.append("")
            lines.append("Agent:")
            lines.append(agent_text)
        lines.append("")

    return "\n".join(lines)


def _join_chunks(chunks: list[str]) -> str:
    return " ".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def _append_unique(values: list[str], candidate: str | None) -> None:
    if not candidate:
        return
    if values and values[-1] == candidate:
        return
    values.append(candidate)


def _render_latency_trail(turn: _TurnSummary) -> list[str]:
    lines: list[str] = []

    merged_delay_ms = _timestamp_delta_ms(turn.merged_at, turn.opened_at)
    if merged_delay_ms is not None:
        if turn.merged_debounce_seconds is not None:
            lines.append(
                f"- Transcript merged {merged_delay_ms:.1f} ms after turn opened "
                f"(debounce target {turn.merged_debounce_seconds * 1000:.1f} ms)"
            )
        else:
            lines.append(
                f"- Transcript merged {merged_delay_ms:.1f} ms after turn opened"
            )

    model_start_delay_ms = _timestamp_delta_ms(turn.model_started_at, turn.opened_at)
    if model_start_delay_ms is not None:
        lines.append(f"- Model started {model_start_delay_ms:.1f} ms after turn opened")

    if turn.first_status_latency_ms is not None:
        line = f"- First model status {turn.first_status_latency_ms:.1f} ms after model start"
        absolute_ms = _timestamp_delta_ms(turn.first_status_at, turn.opened_at)
        if absolute_ms is not None:
            line += f" ({absolute_ms:.1f} ms after turn opened)"
        lines.append(line)

    if turn.first_chunk_latency_ms is not None:
        line = f"- First spoken chunk {turn.first_chunk_latency_ms:.1f} ms after model start"
        absolute_ms = _timestamp_delta_ms(turn.first_chunk_at, turn.opened_at)
        if absolute_ms is not None:
            line += f" ({absolute_ms:.1f} ms after turn opened)"
        lines.append(line)

    if turn.tts_finished_latency_ms is not None:
        line = (
            f"- Speech playout finished {turn.tts_finished_latency_ms:.1f} ms "
            "after model start"
        )
        absolute_ms = _timestamp_delta_ms(turn.tts_finished_at, turn.opened_at)
        if absolute_ms is not None:
            line += f" ({absolute_ms:.1f} ms after turn opened)"
        lines.append(line)

    return lines


def _string_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _timestamp_delta_ms(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return round((later - earlier) * 1000, 1)


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    return (
        "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
        or "session"
    )


def _serialize(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            key: _serialize(inner) for key, inner in dataclasses.asdict(value).items()
        }

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): _serialize(inner) for key, inner in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialize(inner) for inner in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if hasattr(value, "model_dump"):
        return _serialize(value.model_dump())

    if hasattr(value, "__dict__"):
        return _serialize(vars(value))

    return repr(value)
