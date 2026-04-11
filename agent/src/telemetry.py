from __future__ import annotations

import dataclasses
import json
import logging
import time
from pathlib import Path
from typing import Any


logger = logging.getLogger("claude-code-phone-bridge")


class BridgeTelemetry:
    def __init__(self, output_path: str | None = None) -> None:
        self._output_path = Path(output_path).expanduser() if output_path else None
        if self._output_path is not None:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

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
            logger.exception("Failed to persist bridge telemetry", extra={"path": str(self._output_path)})


def _serialize(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {key: _serialize(inner) for key, inner in dataclasses.asdict(value).items()}

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
