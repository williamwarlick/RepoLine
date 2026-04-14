from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOCKET_PREFIX = "rlca"
BRIDGE_CONNECT_TIMEOUT_SECONDS = 1.0
BRIDGE_RESPONSE_TIMEOUT_SECONDS = 3.0


class CursorAppBridgeError(RuntimeError):
    """Raised when the Cursor app bridge is unavailable or rejects a request."""


@dataclass(frozen=True, slots=True)
class CursorAppBridgeState:
    workspace_root: str
    socket_path: str
    state_path: str


@dataclass(frozen=True, slots=True)
class CursorAppBridgeSubmitResult:
    composer_id: str
    via: str


def bridge_state_for_workspace(workspace_root: str | Path) -> CursorAppBridgeState:
    workspace_path = str(Path(workspace_root).expanduser().resolve())
    workspace_hash = hashlib.sha1(workspace_path.encode("utf-8")).hexdigest()
    tmp_dir = Path("/tmp")
    return CursorAppBridgeState(
        workspace_root=workspace_path,
        socket_path=str(tmp_dir / f"{SOCKET_PREFIX}-{workspace_hash}.sock"),
        state_path=str(tmp_dir / f"{SOCKET_PREFIX}-{workspace_hash}.json"),
    )


def load_bridge_state(workspace_root: str | Path) -> CursorAppBridgeState | None:
    state = bridge_state_for_workspace(workspace_root)
    state_path = Path(state.state_path)
    if not state_path.exists():
        return None

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    socket_path = str(payload.get("socketPath") or "").strip()
    workspace_path = str(payload.get("workspacePath") or "").strip()
    if not socket_path or workspace_path != state.workspace_root:
        return None

    return CursorAppBridgeState(
        workspace_root=workspace_path,
        socket_path=socket_path,
        state_path=state.state_path,
    )


async def ping_cursor_app_bridge(
    workspace_root: str | Path,
) -> dict[str, Any] | None:
    state = load_bridge_state(workspace_root)
    if state is None:
        return None
    return await _request_bridge(state, {"method": "ping"})


async def request_cursor_app_bridge(
    *,
    workspace_root: str | Path,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    state = load_bridge_state(workspace_root)
    if state is None:
        return None
    return await _request_bridge(state, payload)


async def submit_prompt_via_cursor_app_bridge(
    *,
    workspace_root: str | Path,
    prompt: str,
    composer_id: str | None = None,
    method: str = "submit",
) -> CursorAppBridgeSubmitResult | None:
    state = load_bridge_state(workspace_root)
    if state is None:
        return None

    request = {"method": method, "prompt": prompt}
    if composer_id:
        request["composerId"] = composer_id

    payload = await _request_bridge(state, request)
    composer_id_value = str(payload.get("composerId") or "").strip()
    via = str(payload.get("via") or "").strip()
    if not composer_id_value or not via:
        raise CursorAppBridgeError(
            "Cursor bridge returned an incomplete submit response."
        )

    return CursorAppBridgeSubmitResult(
        composer_id=composer_id_value,
        via=via,
    )


async def _request_bridge(
    state: CursorAppBridgeState,
    request: dict[str, Any],
) -> dict[str, Any]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(state.socket_path),
            timeout=BRIDGE_CONNECT_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        raise CursorAppBridgeError("Cursor bridge socket is unavailable.") from None

    writer.write(json.dumps(request).encode("utf-8") + b"\n")
    await writer.drain()

    try:
        raw_response = await asyncio.wait_for(
            reader.readline(),
            timeout=BRIDGE_RESPONSE_TIMEOUT_SECONDS,
        )
    finally:
        writer.close()
        await writer.wait_closed()

    if not raw_response:
        raise CursorAppBridgeError("Cursor bridge closed the socket without a response.")

    try:
        response = json.loads(raw_response.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CursorAppBridgeError("Cursor bridge returned invalid JSON.") from exc

    if not response.get("ok"):
        error = response.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
        else:
            message = str(error or "").strip()
        raise CursorAppBridgeError(message or "Cursor bridge request failed.")

    result = response.get("result")
    if not isinstance(result, dict):
        raise CursorAppBridgeError("Cursor bridge returned an invalid result payload.")
    return result
