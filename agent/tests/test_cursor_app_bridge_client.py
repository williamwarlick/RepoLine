from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cursor_app_bridge_client import (
    CursorAppBridgeError,
    bridge_state_for_workspace,
    ensure_cursor_app_bridge,
    load_bridge_state,
    submit_prompt_via_cursor_app_bridge,
)


def test_load_bridge_state_requires_matching_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    expected = bridge_state_for_workspace(workspace)
    Path(expected.state_path).write_text(
        json.dumps(
            {
                "workspacePath": str(tmp_path / "other"),
                "socketPath": expected.socket_path,
            }
        ),
        encoding="utf-8",
    )

    assert load_bridge_state(workspace) is None


@pytest.mark.asyncio
async def test_submit_prompt_via_cursor_app_bridge_returns_submit_result(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = bridge_state_for_workspace(workspace)
    Path(state.state_path).write_text(
        json.dumps(
            {
                "workspacePath": str(workspace),
                "socketPath": state.socket_path,
            }
        ),
        encoding="utf-8",
    )

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads((await reader.readline()).decode("utf-8"))
        assert request == {
            "method": "submitFollowupClipboardAndSend",
            "prompt": "Reply with oak",
            "composerId": "composer-123",
        }
        writer.write(
            json.dumps(
                {
                    "ok": True,
                    "result": {
                        "composerId": "composer-123",
                        "via": "internal-submit",
                    },
                }
            ).encode("utf-8")
            + b"\n"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(_handle, state.socket_path)
    try:
        result = await submit_prompt_via_cursor_app_bridge(
            workspace_root=workspace,
            prompt="Reply with oak",
            composer_id="composer-123",
            method="submitFollowupClipboardAndSend",
        )
    finally:
        server.close()
        await server.wait_closed()

    assert result is not None
    assert result.composer_id == "composer-123"
    assert result.via == "internal-submit"


@pytest.mark.asyncio
async def test_submit_prompt_via_cursor_app_bridge_raises_on_bridge_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = bridge_state_for_workspace(workspace)
    Path(state.state_path).write_text(
        json.dumps(
            {
                "workspacePath": str(workspace),
                "socketPath": state.socket_path,
            }
        ),
        encoding="utf-8",
    )

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        writer.write(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "message": "submitMessage is not callable",
                    },
                }
            ).encode("utf-8")
            + b"\n"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(_handle, state.socket_path)
    try:
        with pytest.raises(CursorAppBridgeError, match="submitMessage is not callable"):
            await submit_prompt_via_cursor_app_bridge(
                workspace_root=workspace,
                prompt="Reply with oak",
            )
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ensure_cursor_app_bridge_reuses_live_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_calls: list[str] = []

    async def fake_ping(workspace_root: str) -> dict[str, object] | None:
        return {"selectedComposerId": "composer-123"}

    async def fake_launch(workspace_root: str) -> None:
        launch_calls.append(workspace_root)

    monkeypatch.setattr("cursor_app_bridge_client.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr("cursor_app_bridge_client._launch_cursor_workspace", fake_launch)

    result = await ensure_cursor_app_bridge("/tmp/repo")

    assert result == {"selectedComposerId": "composer-123"}
    assert launch_calls == []


@pytest.mark.asyncio
async def test_ensure_cursor_app_bridge_opens_cursor_when_bridge_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Path("/tmp/repo").resolve()
    ping_results = [None, None, {"selectedComposerId": "composer-456"}]
    launch_calls: list[str] = []

    async def fake_ping(workspace_root: str) -> dict[str, object] | None:
        return ping_results.pop(0)

    async def fake_launch(workspace_root: str) -> None:
        launch_calls.append(workspace_root)

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("cursor_app_bridge_client.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr("cursor_app_bridge_client._launch_cursor_workspace", fake_launch)
    monkeypatch.setattr("cursor_app_bridge_client.asyncio.sleep", fake_sleep)

    result = await ensure_cursor_app_bridge(workspace)

    assert result == {"selectedComposerId": "composer-456"}
    assert launch_calls == [str(workspace)]
