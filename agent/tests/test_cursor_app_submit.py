from __future__ import annotations

import pytest

from cursor_app_submit import (
    CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT,
    CURSOR_APP_SUBMIT_MODE_BRIDGE_COMPOSER_HANDLE,
    BRIDGE_SUBMIT_METHODS,
    DEFAULT_CURSOR_APP_COMMAND_TITLE,
    CursorAppSubmitError,
    CursorAppSubmitResult,
    CursorUserBubbleMarker,
    submit_prompt_to_cursor_app,
    _bridge_handle_submit_available,
    _bridge_selected_composer_id,
    _bridge_selected_composer_ids,
    _composer_has_history,
    _ensure_selected_composer_id,
    _is_invalid_cursor_connection_error,
    _preferred_candidate_submit_composer_id,
    _resolve_submit_composer_id,
    _submit_mode_attempts_for_bridge_status,
    _try_bridge_active_submit,
    _wait_for_submitted_prompt,
    build_active_input_submit_command,
    build_osascript_submit_command,
    build_shortcut_submit_command,
)


def test_build_osascript_submit_command_uses_focus_followup_title() -> None:
    command = build_osascript_submit_command(prompt="Reply with pong")

    assert command[0] == "osascript"
    assert DEFAULT_CURSOR_APP_COMMAND_TITLE in command
    assert "Reply with pong" in command
    assert "on run argv" in command


def test_build_shortcut_submit_command_uses_cmd_l_and_prompt() -> None:
    command = build_shortcut_submit_command(prompt="Reply with cedar")

    assert command[0] == "osascript"
    assert "Reply with cedar" in command
    assert any(item.strip() == 'keystroke "l" using {command down}' for item in command)


def test_build_active_input_submit_command_replaces_existing_text_before_submit() -> None:
    command = build_active_input_submit_command(prompt="Reply with birch")

    assert command[0] == "osascript"
    assert "Reply with birch" in command
    assert any(item.strip() == 'keystroke "a" using {command down}' for item in command)
    assert any(item.strip() == 'keystroke "v" using {command down}' for item in command)


@pytest.mark.asyncio
async def test_submit_prompt_to_cursor_app_prefers_bridge_composer_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {"selectedComposerId": "composer-123"}

    async def fake_ensure_selected_composer_id(
        workspace_root: str,
        *,
        bridge_status: dict[str, object] | None = None,
        prefer_new_composer: bool = False,
    ) -> str | None:
        return "composer-123"

    bridge_calls: list[str] = []

    async def fake_try_bridge_submit(
        *,
        workspace_root: str,
        prompt: str,
        composer_id: str | None,
        method: str,
    ):
        bridge_calls.append(method)
        return CursorAppSubmitResult(composer_id="composer-123")

    async def fake_try_bridge_active_submit(**kwargs):
        raise AssertionError("active-input fallback should not run")

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._ensure_selected_composer_id",
        fake_ensure_selected_composer_id,
    )
    monkeypatch.setattr(
        "cursor_app_submit._try_bridge_submit",
        fake_try_bridge_submit,
    )
    monkeypatch.setattr(
        "cursor_app_submit._try_bridge_active_submit",
        fake_try_bridge_active_submit,
    )

    result = await submit_prompt_to_cursor_app(
        workspace_root="/tmp/repo",
        prompt="Reply with cedar",
        submit_mode=CURSOR_APP_SUBMIT_MODE_BRIDGE_COMPOSER_HANDLE,
    )

    assert result.composer_id == "composer-123"
    assert bridge_calls == ["submitViaComposerHandle"]


@pytest.mark.asyncio
async def test_submit_prompt_to_cursor_app_uses_active_input_mode_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {"selectedComposerId": "composer-123"}

    async def fake_ensure_selected_composer_id(
        workspace_root: str,
        *,
        bridge_status: dict[str, object] | None = None,
        prefer_new_composer: bool = False,
    ) -> str | None:
        return "composer-123"

    async def fake_try_bridge_submit(**kwargs):
        raise AssertionError("bridge submit should not run")

    async def fake_try_bridge_active_submit(
        *,
        workspace_root: str,
        prompt: str,
        composer_id: str | None,
    ):
        return CursorAppSubmitResult(composer_id="composer-123")

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._ensure_selected_composer_id",
        fake_ensure_selected_composer_id,
    )
    monkeypatch.setattr(
        "cursor_app_submit._try_bridge_submit",
        fake_try_bridge_submit,
    )
    monkeypatch.setattr(
        "cursor_app_submit._try_bridge_active_submit",
        fake_try_bridge_active_submit,
    )

    result = await submit_prompt_to_cursor_app(
        workspace_root="/tmp/repo",
        prompt="Reply with cedar",
        submit_mode=CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT,
    )

    assert result.composer_id == "composer-123"


@pytest.mark.asyncio
async def test_submit_prompt_to_cursor_app_auto_skips_bridge_handle_when_probe_says_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "composer-123",
            "handleProbe": {"hasSubmitMessage": False},
        }

    async def fake_ensure_selected_composer_id(
        workspace_root: str,
        *,
        bridge_status: dict[str, object] | None = None,
        prefer_new_composer: bool = False,
    ) -> str | None:
        return "composer-123"

    async def fake_try_bridge_submit(**kwargs):
        raise AssertionError("bridge handle should not run when probe says unavailable")

    active_calls: list[str | None] = []

    async def fake_try_bridge_active_submit(
        *,
        workspace_root: str,
        prompt: str,
        composer_id: str | None,
    ):
        active_calls.append(composer_id)
        return CursorAppSubmitResult(composer_id="composer-123")

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._ensure_selected_composer_id",
        fake_ensure_selected_composer_id,
    )
    monkeypatch.setattr(
        "cursor_app_submit._try_bridge_submit",
        fake_try_bridge_submit,
    )
    monkeypatch.setattr(
        "cursor_app_submit._try_bridge_active_submit",
        fake_try_bridge_active_submit,
    )

    result = await submit_prompt_to_cursor_app(
        workspace_root="/tmp/repo",
        prompt="Reply with cedar",
        submit_mode="auto",
    )

    assert result.composer_id == "composer-123"
    assert active_calls == ["composer-123"]


def test_bridge_submit_methods_avoid_detached_thread_fallbacks() -> None:
    assert "submitOpenDetachedAndSend" not in BRIDGE_SUBMIT_METHODS
    assert "submitTestOpenDetachedAndSend" not in BRIDGE_SUBMIT_METHODS
    assert "submit" not in BRIDGE_SUBMIT_METHODS


def test_submit_mode_attempts_for_auto_uses_active_input_when_handle_probe_is_missing_or_false() -> None:
    assert _submit_mode_attempts_for_bridge_status(
        "auto",
        bridge_status=None,
    ) == ("active-input",)
    assert _submit_mode_attempts_for_bridge_status(
        "auto",
        bridge_status={"handleProbe": {"hasSubmitMessage": False}},
    ) == ("active-input",)


def test_submit_mode_attempts_for_auto_prefers_bridge_handle_when_probe_is_true() -> None:
    assert _submit_mode_attempts_for_bridge_status(
        "auto",
        bridge_status={"handleProbe": {"hasSubmitMessage": True}},
    ) == ("bridge-composer-handle", "active-input")


def test_bridge_handle_submit_available_requires_positive_probe() -> None:
    assert _bridge_handle_submit_available(None) is False
    assert _bridge_handle_submit_available({}) is False
    assert _bridge_handle_submit_available({"handleProbe": {}}) is False
    assert (
        _bridge_handle_submit_available({"handleProbe": {"hasSubmitMessage": False}})
        is False
    )
    assert (
        _bridge_handle_submit_available({"handleProbe": {"hasSubmitMessage": True}})
        is True
    )


def test_preferred_candidate_submit_composer_id_prefers_history_backed_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "cursor_app_submit._composer_has_history",
        lambda composer_id: composer_id == "real-1",
    )

    assert _preferred_candidate_submit_composer_id(["empty-1", "real-1"]) == "real-1"
    assert _preferred_candidate_submit_composer_id(["empty-1"]) == "empty-1"
    assert _preferred_candidate_submit_composer_id([]) is None


def test_bridge_selected_composer_id_returns_trimmed_id() -> None:
    assert _bridge_selected_composer_id({"selectedComposerId": "  composer-123  "}) == (
        "composer-123"
    )
    assert _bridge_selected_composer_id({"selectedComposerId": ""}) is None
    assert _bridge_selected_composer_id(None) is None


def test_bridge_selected_composer_ids_include_secondary_selected_threads() -> None:
    assert _bridge_selected_composer_ids(
        {
            "selectedComposerId": " empty-1 ",
            "selectedComposerIds": ["empty-1", " real-1 ", "", "empty-1"],
        }
    ) == ["empty-1", "real-1"]
    assert _bridge_selected_composer_ids(None) == []


def test_invalid_cursor_connection_error_matches_applescript_disconnect() -> None:
    assert _is_invalid_cursor_connection_error(
        "execution error: Cursor got an error: Connection is invalid. (-609)"
    )
    assert not _is_invalid_cursor_connection_error("some other failure")


def test_composer_has_history_uses_bubbles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cursor_app_submit._latest_user_marker",
        lambda composer_id: CursorUserBubbleMarker(
            bubble_id="bubble-1",
            text="Hello",
        )
        if composer_id == "composer-123"
        else None,
    )

    assert _composer_has_history("composer-123") is True
    assert _composer_has_history("composer-empty") is False


@pytest.mark.asyncio
async def test_resolve_submit_composer_id_skips_empty_selected_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = [
        {"selectedComposerId": "empty-1"},
        {"selectedComposerId": "empty-2"},
        {"selectedComposerId": "real-1"},
    ]
    exec_calls: list[dict[str, object]] = []

    async def fake_ping(workspace_root: str) -> dict[str, object]:
        return statuses[0]

    async def fake_request_cursor_app_bridge(
        *,
        workspace_root: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        exec_calls.append(payload)
        statuses.pop(0)
        return {"ok": True}

    monkeypatch.setattr("cursor_app_submit.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr(
        "cursor_app_submit.request_cursor_app_bridge",
        fake_request_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._composer_has_history",
        lambda composer_id: composer_id == "real-1",
    )
    monkeypatch.setattr(
        "cursor_app_submit._safe_find_active_composer_id",
        lambda workspace_root: None,
    )

    composer_id = await _resolve_submit_composer_id("/tmp/repo")

    assert composer_id == "real-1"
    assert exec_calls == [
        {
            "method": "exec",
            "command": "composer.selectPreviousComposer",
            "args": [],
        },
        {
            "method": "exec",
            "command": "composer.selectPreviousComposer",
            "args": [],
        },
    ]


@pytest.mark.asyncio
async def test_ensure_selected_composer_id_reuses_current_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {"selectedComposerId": "composer-123"}

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )

    composer_id = await _ensure_selected_composer_id("/tmp/repo")

    assert composer_id == "composer-123"


@pytest.mark.asyncio
async def test_ensure_selected_composer_id_prefers_selected_composer_with_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "empty-1",
            "selectedComposerIds": ["empty-1", "real-1"],
        }

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._safe_find_active_composer_id",
        lambda workspace_root: None,
    )
    monkeypatch.setattr(
        "cursor_app_submit._composer_has_history",
        lambda composer_id: composer_id == "real-1",
    )

    composer_id = await _ensure_selected_composer_id("/tmp/repo")

    assert composer_id == "real-1"


@pytest.mark.asyncio
async def test_ensure_selected_composer_id_creates_new_composer_when_none_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge_statuses = [
        {"selectedComposerId": ""},
        {"selectedComposerId": ""},
        {"selectedComposerId": "composer-new"},
    ]
    exec_calls: list[dict[str, object]] = []

    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return bridge_statuses.pop(0)

    async def fake_request_cursor_app_bridge(
        *,
        workspace_root: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        exec_calls.append(payload)
        return {"ok": True}

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit.request_cursor_app_bridge",
        fake_request_cursor_app_bridge,
    )
    monkeypatch.setattr("cursor_app_submit.asyncio.sleep", fake_sleep)

    composer_id = await _ensure_selected_composer_id("/tmp/repo")

    assert composer_id == "composer-new"
    assert exec_calls == [
        {
            "method": "exec",
            "command": "composer.createNew",
            "args": [],
        }
    ]


@pytest.mark.asyncio
async def test_ensure_selected_composer_id_can_force_new_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge_statuses = [
        {"selectedComposerId": "composer-old"},
        {"selectedComposerId": "composer-old"},
        {"selectedComposerId": "composer-new"},
    ]
    exec_calls: list[dict[str, object]] = []

    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return bridge_statuses.pop(0)

    async def fake_request_cursor_app_bridge(
        *,
        workspace_root: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        exec_calls.append(payload)
        return {"ok": True}

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit.request_cursor_app_bridge",
        fake_request_cursor_app_bridge,
    )
    monkeypatch.setattr("cursor_app_submit.asyncio.sleep", fake_sleep)

    composer_id = await _ensure_selected_composer_id(
        "/tmp/repo",
        prefer_new_composer=True,
    )

    assert composer_id == "composer-new"
    assert exec_calls == [
        {
            "method": "exec",
            "command": "composer.createNew",
            "args": [],
        }
    ]


@pytest.mark.asyncio
async def test_submit_prompt_to_cursor_app_fails_when_fresh_composer_never_appears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {"selectedComposerId": "composer-old"}

    async def fake_ensure_selected_composer_id(
        workspace_root: str,
        *,
        bridge_status: dict[str, object] | None = None,
        prefer_new_composer: bool = False,
    ) -> str | None:
        assert prefer_new_composer is True
        return None

    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._ensure_selected_composer_id",
        fake_ensure_selected_composer_id,
    )

    with pytest.raises(CursorAppSubmitError, match="fresh composer"):
        await submit_prompt_to_cursor_app(
            workspace_root="/tmp/repo",
            prompt="Reply with cedar",
            submit_mode="auto",
            start_new_composer=True,
        )


@pytest.mark.asyncio
async def test_wait_for_submitted_prompt_accepts_repeated_same_text_with_new_bubble(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = [
        CursorUserBubbleMarker(bubble_id="bubble-1", text="Yeah."),
        CursorUserBubbleMarker(bubble_id="bubble-2", text="Yeah."),
    ]

    monkeypatch.setattr(
        "cursor_app_submit._safe_find_active_composer_id",
        lambda workspace_root: "composer-123",
    )
    async def fake_ping(workspace_root: str) -> dict[str, object]:
        return {"selectedComposerId": "composer-123"}

    monkeypatch.setattr("cursor_app_submit.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr(
        "cursor_app_submit._latest_user_marker",
        lambda composer_id: markers[0] if len(markers) == 2 else markers[-1],
    )

    async def fake_sleep(_: float) -> None:
        markers.pop(0)

    monkeypatch.setattr("cursor_app_submit.asyncio.sleep", fake_sleep)

    result = await _wait_for_submitted_prompt(
        workspace_root="/tmp/repo",
        prompt="Yeah.",
        baseline_user_markers={
            "composer-123": CursorUserBubbleMarker(
                bubble_id="bubble-1",
                text="Yeah.",
            )
        },
        fallback_composer_id="composer-123",
        timeout_seconds=0.2,
    )

    assert result is not None
    assert result.composer_id == "composer-123"
    assert result.user_bubble_id == "bubble-2"


@pytest.mark.asyncio
async def test_wait_for_submitted_prompt_checks_all_selected_bridge_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "cursor_app_submit._safe_find_active_composer_id",
        lambda workspace_root: "empty-1",
    )

    async def fake_ping(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "empty-1",
            "selectedComposerIds": ["empty-1", "real-1"],
        }

    monkeypatch.setattr("cursor_app_submit.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr(
        "cursor_app_submit._latest_user_marker",
        lambda composer_id: CursorUserBubbleMarker(
            bubble_id="bubble-real",
            text="Say hi",
        )
        if composer_id == "real-1"
        else None,
    )

    result = await _wait_for_submitted_prompt(
        workspace_root="/tmp/repo",
        prompt="Say hi",
        baseline_user_markers={},
        fallback_composer_id="empty-1",
        timeout_seconds=0.1,
    )

    assert result is not None
    assert result.composer_id == "real-1"
    assert result.user_bubble_id == "bubble-real"


@pytest.mark.asyncio
async def test_try_bridge_active_submit_returns_verified_secondary_selected_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_calls: list[dict[str, object]] = []

    async def fake_ping(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "empty-1",
            "selectedComposerIds": ["empty-1", "real-1"],
        }

    async def fake_request_cursor_app_bridge(
        *,
        workspace_root: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        request_calls.append(payload)
        return {"ok": True}

    async def fake_run_active_input_osascript(**kwargs):
        return None

    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "empty-1",
            "selectedComposerIds": ["empty-1", "real-1"],
        }

    async def fake_wait_for_submitted_prompt(**kwargs):
        return CursorAppSubmitResult(composer_id="real-1")

    monkeypatch.setattr("cursor_app_submit.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr(
        "cursor_app_submit.request_cursor_app_bridge",
        fake_request_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._run_active_input_osascript",
        fake_run_active_input_osascript,
    )
    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._wait_for_submitted_prompt",
        fake_wait_for_submitted_prompt,
    )
    monkeypatch.setattr(
        "cursor_app_submit._latest_user_marker",
        lambda composer_id: None,
    )
    monkeypatch.setattr(
        "cursor_app_submit._safe_find_active_composer_id",
        lambda workspace_root: "empty-1",
    )

    result = await _try_bridge_active_submit(
        workspace_root="/tmp/repo",
        prompt="Say hi",
        composer_id="empty-1",
    )

    assert result is not None
    assert result.composer_id == "real-1"
    assert request_calls == [
        {
            "method": "exec",
            "command": "composer.focusComposer",
            "args": [],
        }
    ]


@pytest.mark.asyncio
async def test_try_bridge_active_submit_fallback_prefers_history_backed_selected_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ping(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "empty-1",
            "selectedComposerIds": ["empty-1", "real-1"],
        }

    async def fake_request_cursor_app_bridge(
        *,
        workspace_root: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {"ok": True}

    async def fake_run_active_input_osascript(**kwargs):
        return None

    async def fake_ensure_cursor_app_bridge(workspace_root: str) -> dict[str, object]:
        return {
            "selectedComposerId": "empty-1",
            "selectedComposerIds": ["empty-1", "real-1"],
        }

    async def fake_wait_for_submitted_prompt(**kwargs):
        return None

    monkeypatch.setattr("cursor_app_submit.ping_cursor_app_bridge", fake_ping)
    monkeypatch.setattr(
        "cursor_app_submit.request_cursor_app_bridge",
        fake_request_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._run_active_input_osascript",
        fake_run_active_input_osascript,
    )
    monkeypatch.setattr(
        "cursor_app_submit.ensure_cursor_app_bridge",
        fake_ensure_cursor_app_bridge,
    )
    monkeypatch.setattr(
        "cursor_app_submit._wait_for_submitted_prompt",
        fake_wait_for_submitted_prompt,
    )
    monkeypatch.setattr(
        "cursor_app_submit._latest_user_marker",
        lambda composer_id: None,
    )
    monkeypatch.setattr(
        "cursor_app_submit._safe_find_active_composer_id",
        lambda workspace_root: None,
    )
    monkeypatch.setattr(
        "cursor_app_submit._composer_has_history",
        lambda composer_id: composer_id == "real-1",
    )

    result = await _try_bridge_active_submit(
        workspace_root="/tmp/repo",
        prompt="Say hi",
        composer_id="empty-1",
    )

    assert result is not None
    assert result.composer_id == "real-1"
