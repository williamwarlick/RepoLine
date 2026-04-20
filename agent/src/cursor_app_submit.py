from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from cursor_app_bridge_client import (
    CursorAppBridgeError,
    ensure_cursor_app_bridge,
    ping_cursor_app_bridge,
    request_cursor_app_bridge,
    submit_prompt_via_cursor_app_bridge,
)
from cursor_app_tap import CursorAppTapError, find_active_composer_id, load_bubbles

DEFAULT_CURSOR_APP_COMMAND_TITLE = "Focus Chat Followup"
DEFAULT_CURSOR_APP_SUBMIT_MODE = "auto"
CURSOR_APP_SUBMIT_MODE_BRIDGE_COMPOSER_HANDLE = "bridge-composer-handle"
CURSOR_APP_SUBMIT_MODE_BRIDGE_SUBMIT = "bridge-submit"
CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT = "active-input"
FAST_SHORTCUT_ACTIVATE_DELAY_SECONDS = 0.15
FAST_SHORTCUT_PASTE_DELAY_SECONDS = 0.08
FAST_SHORTCUT_SUBMIT_DELAY_SECONDS = 0.04
FAST_ACTIVE_INPUT_SELECT_DELAY_SECONDS = 0.03
FAST_ACTIVE_INPUT_PASTE_DELAY_SECONDS = 0.05
FAST_ACTIVE_INPUT_SUBMIT_DELAY_SECONDS = 0.04
FAST_ACTIVATE_DELAY_SECONDS = 0.2
FAST_PALETTE_TYPE_DELAY_SECONDS = 0.12
FAST_COMMAND_CONFIRM_DELAY_SECONDS = 0.15
FAST_PASTE_DELAY_SECONDS = 0.18
FAST_SUBMIT_DELAY_SECONDS = 0.05
FALLBACK_ACTIVATE_DELAY_SECONDS = 0.6
FALLBACK_PALETTE_TYPE_DELAY_SECONDS = 0.35
FALLBACK_COMMAND_CONFIRM_DELAY_SECONDS = 0.45
FALLBACK_PASTE_DELAY_SECONDS = 0.55
FALLBACK_SUBMIT_DELAY_SECONDS = 0.15
WORKSPACE_REFocus_DELAY_SECONDS = 0.75
FAST_SUBMIT_VERIFICATION_TIMEOUT_SECONDS = 0.9
FALLBACK_SUBMIT_VERIFICATION_TIMEOUT_SECONDS = 3.0
SUBMIT_VERIFICATION_POLL_INTERVAL_SECONDS = 0.05
BRIDGE_SUBMIT_VERIFICATION_TIMEOUT_SECONDS = 1.35
BRIDGE_COMPOSER_SCAN_STEPS = 6
CURSOR_CONNECTION_INVALID_SNIPPET = "Connection is invalid"
BRIDGE_SUBMIT_METHODS: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CursorAppSubmitResult:
    composer_id: str
    user_bubble_id: str | None = None


@dataclass(frozen=True, slots=True)
class CursorUserBubbleMarker:
    bubble_id: str
    text: str


def _build_osascript_lines(
    *,
    activate_delay_seconds: float,
    palette_type_delay_seconds: float,
    command_confirm_delay_seconds: float,
    paste_delay_seconds: float,
    submit_delay_seconds: float,
) -> list[str]:
    return [
        "on run argv",
        "  set commandTitle to item 1 of argv",
        "  set promptText to item 2 of argv",
        "  set the clipboard to promptText",
        '  tell application "Cursor" to activate',
        f"  delay {activate_delay_seconds}",
        '  tell application "System Events"',
        '    tell process "Cursor"',
        "      set frontmost to true",
        '      keystroke "p" using {command down, shift down}',
        f"      delay {palette_type_delay_seconds}",
        "      keystroke commandTitle",
        f"      delay {command_confirm_delay_seconds}",
        "      key code 36",
        f"      delay {paste_delay_seconds}",
        '      keystroke "v" using {command down}',
        f"      delay {submit_delay_seconds}",
        "      key code 36",
        "    end tell",
        "  end tell",
        "end run",
    ]


def _build_shortcut_submit_osascript_lines(
    *,
    activate_delay_seconds: float,
    paste_delay_seconds: float,
    submit_delay_seconds: float,
) -> list[str]:
    return [
        "on run argv",
        "  set promptText to item 1 of argv",
        "  set the clipboard to promptText",
        '  tell application "Cursor" to activate',
        f"  delay {activate_delay_seconds}",
        '  tell application "System Events"',
        '    tell process "Cursor"',
        "      set frontmost to true",
        '      keystroke "l" using {command down}',
        f"      delay {paste_delay_seconds}",
        '      keystroke "v" using {command down}',
        f"      delay {submit_delay_seconds}",
        "      key code 36",
        "    end tell",
        "  end tell",
        "end run",
    ]


class CursorAppSubmitError(RuntimeError):
    """Raised when RepoLine cannot submit a prompt into the Cursor app."""


def build_osascript_submit_command(
    *,
    prompt: str,
    command_title: str = DEFAULT_CURSOR_APP_COMMAND_TITLE,
    activate_delay_seconds: float = FAST_ACTIVATE_DELAY_SECONDS,
    palette_type_delay_seconds: float = FAST_PALETTE_TYPE_DELAY_SECONDS,
    command_confirm_delay_seconds: float = FAST_COMMAND_CONFIRM_DELAY_SECONDS,
    paste_delay_seconds: float = FAST_PASTE_DELAY_SECONDS,
    submit_delay_seconds: float = FAST_SUBMIT_DELAY_SECONDS,
) -> list[str]:
    cmd = ["osascript"]
    for line in _build_osascript_lines(
        activate_delay_seconds=activate_delay_seconds,
        palette_type_delay_seconds=palette_type_delay_seconds,
        command_confirm_delay_seconds=command_confirm_delay_seconds,
        paste_delay_seconds=paste_delay_seconds,
        submit_delay_seconds=submit_delay_seconds,
    ):
        cmd.extend(["-e", line])
    cmd.extend([command_title, prompt])
    return cmd


def build_shortcut_submit_command(
    *,
    prompt: str,
    activate_delay_seconds: float = FAST_SHORTCUT_ACTIVATE_DELAY_SECONDS,
    paste_delay_seconds: float = FAST_SHORTCUT_PASTE_DELAY_SECONDS,
    submit_delay_seconds: float = FAST_SHORTCUT_SUBMIT_DELAY_SECONDS,
) -> list[str]:
    cmd = ["osascript"]
    for line in _build_shortcut_submit_osascript_lines(
        activate_delay_seconds=activate_delay_seconds,
        paste_delay_seconds=paste_delay_seconds,
        submit_delay_seconds=submit_delay_seconds,
    ):
        cmd.extend(["-e", line])
    cmd.append(prompt)
    return cmd


def build_active_input_submit_command(
    *,
    prompt: str,
    activate_delay_seconds: float = FAST_SHORTCUT_ACTIVATE_DELAY_SECONDS,
    select_delay_seconds: float = FAST_ACTIVE_INPUT_SELECT_DELAY_SECONDS,
    paste_delay_seconds: float = FAST_ACTIVE_INPUT_PASTE_DELAY_SECONDS,
    submit_delay_seconds: float = FAST_ACTIVE_INPUT_SUBMIT_DELAY_SECONDS,
) -> list[str]:
    return [
        "osascript",
        "-e",
        "on run argv",
        "-e",
        "  set promptText to item 1 of argv",
        "-e",
        "  set the clipboard to promptText",
        "-e",
        '  tell application "Cursor" to activate',
        "-e",
        f"  delay {activate_delay_seconds}",
        "-e",
        '  tell application "System Events"',
        "-e",
        '    tell process "Cursor"',
        "-e",
        "      set frontmost to true",
        "-e",
        '      keystroke "a" using {command down}',
        "-e",
        f"      delay {select_delay_seconds}",
        "-e",
        '      keystroke "v" using {command down}',
        "-e",
        f"      delay {paste_delay_seconds}",
        "-e",
        "      key code 36",
        "-e",
        f"      delay {submit_delay_seconds}",
        "-e",
        "    end tell",
        "-e",
        "  end tell",
        "-e",
        "end run",
        prompt,
    ]


async def submit_prompt_to_cursor_app(
    *,
    workspace_root: str | Path,
    prompt: str,
    command_title: str = DEFAULT_CURSOR_APP_COMMAND_TITLE,
    submit_mode: str | None = DEFAULT_CURSOR_APP_SUBMIT_MODE,
    start_new_composer: bool = False,
) -> CursorAppSubmitResult:
    workspace_path = str(Path(workspace_root).expanduser().resolve())
    bridge_status = await ensure_cursor_app_bridge(workspace_path)
    composer_id = await _ensure_selected_composer_id(
        workspace_path,
        bridge_status=bridge_status,
        prefer_new_composer=start_new_composer,
    )
    if start_new_composer and not composer_id:
        raise CursorAppSubmitError(
            "Cursor app did not switch to a fresh composer for this benchmark turn."
        )
    resolved_submit_mode = _normalize_submit_mode(submit_mode)

    for attempt_mode in _submit_mode_attempts_for_bridge_status(
        resolved_submit_mode,
        bridge_status=bridge_status,
    ):
        if attempt_mode in {
            CURSOR_APP_SUBMIT_MODE_BRIDGE_COMPOSER_HANDLE,
            CURSOR_APP_SUBMIT_MODE_BRIDGE_SUBMIT,
        }:
            bridge_method = _bridge_method_for_submit_mode(attempt_mode)
            bridge_submit_result = await _try_bridge_submit(
                workspace_root=workspace_path,
                prompt=prompt,
                composer_id=composer_id,
                method=bridge_method,
            )
            if bridge_submit_result is not None:
                return bridge_submit_result

            if resolved_submit_mode != DEFAULT_CURSOR_APP_SUBMIT_MODE:
                raise CursorAppSubmitError(
                    f"Cursor app did not accept the prompt via {attempt_mode}."
                )
            continue

        active_submit_result = await _try_bridge_active_submit(
            workspace_root=workspace_path,
            prompt=prompt,
            composer_id=composer_id,
        )
        if active_submit_result is not None:
            return active_submit_result

        if resolved_submit_mode == CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT:
            raise CursorAppSubmitError(
                "Cursor app did not accept the prompt into the active composer input."
            )

    raise CursorAppSubmitError(
        "Cursor app did not accept the prompt through the direct bridge or active composer input."
    )


def _normalize_submit_mode(value: str | None) -> str:
    normalized = (value or DEFAULT_CURSOR_APP_SUBMIT_MODE).strip().lower()
    if normalized not in {
        DEFAULT_CURSOR_APP_SUBMIT_MODE,
        CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT,
        CURSOR_APP_SUBMIT_MODE_BRIDGE_COMPOSER_HANDLE,
        CURSOR_APP_SUBMIT_MODE_BRIDGE_SUBMIT,
    }:
        raise CursorAppSubmitError(
            "Cursor app submit mode must be one of: "
            "auto, active-input, bridge-composer-handle, bridge-submit."
        )
    return normalized


def _bridge_method_for_submit_mode(submit_mode: str) -> str:
    if submit_mode == CURSOR_APP_SUBMIT_MODE_BRIDGE_SUBMIT:
        return "submit"
    return "submitViaComposerHandle"


def _submit_mode_attempts_for_bridge_status(
    submit_mode: str,
    *,
    bridge_status: dict[str, object] | None,
) -> tuple[str, ...]:
    if submit_mode != DEFAULT_CURSOR_APP_SUBMIT_MODE:
        return (submit_mode,)

    if _bridge_handle_submit_available(bridge_status):
        return (
            CURSOR_APP_SUBMIT_MODE_BRIDGE_COMPOSER_HANDLE,
            CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT,
        )

    return (CURSOR_APP_SUBMIT_MODE_ACTIVE_INPUT,)


def _bridge_handle_submit_available(bridge_status: dict[str, object] | None) -> bool:
    if not isinstance(bridge_status, dict):
        return False

    handle_probe = bridge_status.get("handleProbe")
    if not isinstance(handle_probe, dict):
        return False

    has_submit_message = handle_probe.get("hasSubmitMessage")
    return bool(has_submit_message)


async def _run_submit_osascript(
    *,
    prompt: str,
    command_title: str,
    activate_delay_seconds: float = FAST_ACTIVATE_DELAY_SECONDS,
    palette_type_delay_seconds: float = FAST_PALETTE_TYPE_DELAY_SECONDS,
    command_confirm_delay_seconds: float = FAST_COMMAND_CONFIRM_DELAY_SECONDS,
    paste_delay_seconds: float = FAST_PASTE_DELAY_SECONDS,
    submit_delay_seconds: float = FAST_SUBMIT_DELAY_SECONDS,
) -> str | None:
    submit_proc = await asyncio.create_subprocess_exec(
        *build_osascript_submit_command(
            prompt=prompt,
            command_title=command_title,
            activate_delay_seconds=activate_delay_seconds,
            palette_type_delay_seconds=palette_type_delay_seconds,
            command_confirm_delay_seconds=command_confirm_delay_seconds,
            paste_delay_seconds=paste_delay_seconds,
            submit_delay_seconds=submit_delay_seconds,
        ),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, submit_stderr = await submit_proc.communicate()
    if submit_proc.returncode in {0, None}:
        return None
    return (
        submit_stderr.decode("utf-8", errors="replace").strip()
        or "Failed to submit the prompt through the Cursor app."
    )


async def _run_shortcut_osascript(
    *,
    prompt: str,
    activate_delay_seconds: float = FAST_SHORTCUT_ACTIVATE_DELAY_SECONDS,
    paste_delay_seconds: float = FAST_SHORTCUT_PASTE_DELAY_SECONDS,
    submit_delay_seconds: float = FAST_SHORTCUT_SUBMIT_DELAY_SECONDS,
) -> str | None:
    submit_proc = await asyncio.create_subprocess_exec(
        *build_shortcut_submit_command(
            prompt=prompt,
            activate_delay_seconds=activate_delay_seconds,
            paste_delay_seconds=paste_delay_seconds,
            submit_delay_seconds=submit_delay_seconds,
        ),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, submit_stderr = await submit_proc.communicate()
    if submit_proc.returncode in {0, None}:
        return None
    return (
        submit_stderr.decode("utf-8", errors="replace").strip()
        or "Failed to submit the prompt through the Cursor app shortcut."
    )


def _safe_find_active_composer_id(workspace_root: str) -> str | None:
    try:
        return find_active_composer_id(workspace_root)
    except CursorAppTapError:
        return None


def _latest_user_marker(composer_id: str | None) -> CursorUserBubbleMarker | None:
    if not composer_id:
        return None
    try:
        bubbles = load_bubbles(composer_id)
    except CursorAppTapError:
        return None
    for bubble in reversed(bubbles):
        if bubble.role == "user" and bubble.text.strip():
            return CursorUserBubbleMarker(
                bubble_id=bubble.bubble_id,
                text=bubble.text.strip(),
            )
    return None


async def _try_bridge_submit(
    *,
    workspace_root: str,
    prompt: str,
    composer_id: str | None,
    method: str,
) -> CursorAppSubmitResult | None:
    bridge_status = await ping_cursor_app_bridge(workspace_root)
    baseline_user_markers = _baseline_latest_user_markers(
        workspace_root=workspace_root,
        bridge_status=bridge_status,
        fallback_composer_id=composer_id,
    )

    try:
        submit_result = await submit_prompt_via_cursor_app_bridge(
            workspace_root=workspace_root,
            prompt=prompt,
            composer_id=composer_id,
            method=method,
        )
    except CursorAppBridgeError:
        return None

    if submit_result is None:
        return None

    verified_result = await _wait_for_submitted_prompt(
        workspace_root=workspace_root,
        prompt=prompt,
        baseline_user_markers=baseline_user_markers,
        fallback_composer_id=submit_result.composer_id,
        timeout_seconds=BRIDGE_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
    )
    if verified_result is not None:
        return verified_result

    return CursorAppSubmitResult(composer_id=submit_result.composer_id)


async def _try_bridge_active_submit(
    *,
    workspace_root: str,
    prompt: str,
    composer_id: str | None,
) -> CursorAppSubmitResult | None:
    bridge_status = await ping_cursor_app_bridge(workspace_root)
    baseline_user_markers = _baseline_latest_user_markers(
        workspace_root=workspace_root,
        bridge_status=bridge_status,
        fallback_composer_id=composer_id,
    )
    try:
        await request_cursor_app_bridge(
            workspace_root=workspace_root,
            payload={"method": "exec", "command": "composer.focusComposer", "args": []},
        )
    except CursorAppBridgeError:
        return None

    active_submit_error = await _run_active_input_osascript(prompt=prompt)
    if _is_invalid_cursor_connection_error(active_submit_error):
        try:
            await _refocus_cursor_workspace(workspace_root)
            await ensure_cursor_app_bridge(workspace_root)
            await request_cursor_app_bridge(
                workspace_root=workspace_root,
                payload={
                    "method": "exec",
                    "command": "composer.focusComposer",
                    "args": [],
                },
            )
        except CursorAppBridgeError:
            return None
        active_submit_error = await _run_active_input_osascript(
            prompt=prompt,
            activate_delay_seconds=FALLBACK_ACTIVATE_DELAY_SECONDS,
            select_delay_seconds=FAST_ACTIVE_INPUT_SELECT_DELAY_SECONDS,
            paste_delay_seconds=FALLBACK_PASTE_DELAY_SECONDS,
            submit_delay_seconds=FALLBACK_SUBMIT_DELAY_SECONDS,
    )
    if active_submit_error is not None:
        return None

    active_bridge_status = await ensure_cursor_app_bridge(workspace_root)
    verified_result = await _wait_for_submitted_prompt(
        workspace_root=workspace_root,
        prompt=prompt,
        baseline_user_markers=baseline_user_markers,
        fallback_composer_id=(
            _bridge_selected_composer_id(active_bridge_status) or composer_id
        ),
        timeout_seconds=FALLBACK_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
    )
    if verified_result is not None:
        return verified_result

    active_composer_ids = _candidate_submit_composer_ids(
        bridge_status=active_bridge_status,
        active_composer_id=_safe_find_active_composer_id(workspace_root),
        fallback_composer_id=composer_id,
    )
    resolved_composer_id = _preferred_candidate_submit_composer_id(active_composer_ids)
    if not resolved_composer_id:
        return None

    return CursorAppSubmitResult(composer_id=resolved_composer_id)


async def _ensure_selected_composer_id(
    workspace_root: str,
    *,
    bridge_status: dict[str, object] | None = None,
    prefer_new_composer: bool = False,
) -> str | None:
    current_bridge_status = (
        bridge_status
        if bridge_status is not None
        else await ensure_cursor_app_bridge(workspace_root)
    )
    initial_candidate_ids = _candidate_submit_composer_ids(
        bridge_status=current_bridge_status,
        active_composer_id=_safe_find_active_composer_id(workspace_root),
        fallback_composer_id=None,
    )
    previous_composer_ids = set(initial_candidate_ids)
    if not prefer_new_composer:
        selected_composer_id = _preferred_candidate_submit_composer_id(
            initial_candidate_ids
        )
        if selected_composer_id:
            return selected_composer_id

    try:
        await request_cursor_app_bridge(
            workspace_root=workspace_root,
            payload={
                "method": "exec",
                "command": "composer.createNew",
                "args": [],
            },
        )
    except CursorAppBridgeError:
        return _safe_find_active_composer_id(workspace_root)

    deadline = asyncio.get_running_loop().time() + 3.0
    while asyncio.get_running_loop().time() < deadline:
        current_bridge_status = await ensure_cursor_app_bridge(workspace_root)
        selected_composer_id = _bridge_selected_composer_id(current_bridge_status)
        if selected_composer_id and (
            not prefer_new_composer or selected_composer_id not in previous_composer_ids
        ):
            return selected_composer_id
        active_composer_id = _safe_find_active_composer_id(workspace_root)
        if active_composer_id and (
            not prefer_new_composer or active_composer_id not in previous_composer_ids
        ):
            return active_composer_id
        await asyncio.sleep(SUBMIT_VERIFICATION_POLL_INTERVAL_SECONDS)

    fallback_composer_id = _safe_find_active_composer_id(workspace_root)
    if fallback_composer_id and (
        not prefer_new_composer or fallback_composer_id not in previous_composer_ids
    ):
        return fallback_composer_id
    return None if prefer_new_composer else fallback_composer_id


async def _run_active_input_osascript(
    *,
    prompt: str,
    activate_delay_seconds: float = FAST_SHORTCUT_ACTIVATE_DELAY_SECONDS,
    select_delay_seconds: float = FAST_ACTIVE_INPUT_SELECT_DELAY_SECONDS,
    paste_delay_seconds: float = FAST_ACTIVE_INPUT_PASTE_DELAY_SECONDS,
    submit_delay_seconds: float = FAST_ACTIVE_INPUT_SUBMIT_DELAY_SECONDS,
) -> str | None:
    submit_proc = await asyncio.create_subprocess_exec(
        *build_active_input_submit_command(
            prompt=prompt,
            activate_delay_seconds=activate_delay_seconds,
            select_delay_seconds=select_delay_seconds,
            paste_delay_seconds=paste_delay_seconds,
            submit_delay_seconds=submit_delay_seconds,
        ),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, submit_stderr = await submit_proc.communicate()
    if submit_proc.returncode in {0, None}:
        return None
    return (
        submit_stderr.decode("utf-8", errors="replace").strip()
        or "Failed to submit the prompt into the active Cursor input."
    )


def _baseline_latest_user_markers(
    *,
    workspace_root: str,
    bridge_status: dict[str, object] | None,
    fallback_composer_id: str | None,
) -> dict[str, CursorUserBubbleMarker | None]:
    active_composer_id = _safe_find_active_composer_id(workspace_root)
    return {
        composer_id: _latest_user_marker(composer_id)
        for composer_id in _candidate_submit_composer_ids(
            bridge_status=bridge_status,
            active_composer_id=active_composer_id,
            fallback_composer_id=fallback_composer_id,
        )
    }


async def _wait_for_submitted_prompt(
    *,
    workspace_root: str,
    prompt: str,
    baseline_user_markers: dict[str, CursorUserBubbleMarker | None],
    fallback_composer_id: str | None,
    timeout_seconds: float,
) -> CursorAppSubmitResult | None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    normalized_prompt = prompt.strip()

    while asyncio.get_running_loop().time() < deadline:
        bridge_status = await ping_cursor_app_bridge(workspace_root)
        active_composer_id = _safe_find_active_composer_id(workspace_root)
        candidate_ids = _candidate_submit_composer_ids(
            bridge_status=bridge_status,
            active_composer_id=active_composer_id,
            fallback_composer_id=fallback_composer_id,
        )

        for composer_id in candidate_ids:
            latest_user_marker = _latest_user_marker(composer_id)
            if latest_user_marker is None:
                continue
            if latest_user_marker.text != normalized_prompt:
                continue
            baseline_marker = baseline_user_markers.get(composer_id)
            if (
                baseline_marker is not None
                and baseline_marker.bubble_id == latest_user_marker.bubble_id
            ):
                continue
            return CursorAppSubmitResult(
                composer_id=composer_id,
                user_bubble_id=latest_user_marker.bubble_id,
            )

        await asyncio.sleep(SUBMIT_VERIFICATION_POLL_INTERVAL_SECONDS)

    return None


async def _resolve_submit_composer_id(workspace_root: str) -> str | None:
    bridge_status = await ping_cursor_app_bridge(workspace_root)
    selected_composer_id = _bridge_selected_composer_id(bridge_status)
    if _composer_has_history(selected_composer_id):
        return selected_composer_id

    if bridge_status is not None and selected_composer_id:
        seen = {selected_composer_id}
        for _ in range(BRIDGE_COMPOSER_SCAN_STEPS):
            try:
                await request_cursor_app_bridge(
                    workspace_root=workspace_root,
                    payload={
                        "method": "exec",
                        "command": "composer.selectPreviousComposer",
                        "args": [],
                    },
                )
            except CursorAppBridgeError:
                break
            bridge_status = await ping_cursor_app_bridge(workspace_root)
            candidate_id = _bridge_selected_composer_id(bridge_status)
            if not candidate_id or candidate_id in seen:
                break
            seen.add(candidate_id)
            if _composer_has_history(candidate_id):
                return candidate_id

    fallback_composer_id = _safe_find_active_composer_id(workspace_root)
    if _composer_has_history(fallback_composer_id):
        return fallback_composer_id
    return selected_composer_id or fallback_composer_id


def _is_invalid_cursor_connection_error(error_message: str | None) -> bool:
    if not error_message:
        return False
    return CURSOR_CONNECTION_INVALID_SNIPPET in error_message or "(-609)" in error_message


async def _refocus_cursor_workspace(workspace_root: str) -> None:
    focus_proc = await asyncio.create_subprocess_exec(
        "cursor",
        "-r",
        workspace_root,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, focus_stderr = await focus_proc.communicate()
    if focus_proc.returncode not in {0, None}:
        message = focus_stderr.decode("utf-8", errors="replace").strip()
        raise CursorAppSubmitError(
            message or f"Failed to focus Cursor workspace: {workspace_root}"
        )

    await asyncio.sleep(WORKSPACE_REFocus_DELAY_SECONDS)


def _bridge_selected_composer_id(bridge_status: dict[str, object] | None) -> str | None:
    selected_composer_ids = _bridge_selected_composer_ids(bridge_status)
    return selected_composer_ids[0] if selected_composer_ids else None


def _bridge_selected_composer_ids(bridge_status: dict[str, object] | None) -> list[str]:
    if not isinstance(bridge_status, dict):
        return []

    selected_ids: list[str] = []
    selected_composer_id = bridge_status.get("selectedComposerId")
    if isinstance(selected_composer_id, str):
        normalized_id = selected_composer_id.strip()
        if normalized_id:
            selected_ids.append(normalized_id)

    raw_selected_ids = bridge_status.get("selectedComposerIds")
    if isinstance(raw_selected_ids, list):
        for value in raw_selected_ids:
            if not isinstance(value, str):
                continue
            normalized_id = value.strip()
            if normalized_id and normalized_id not in selected_ids:
                selected_ids.append(normalized_id)

    return selected_ids


def _candidate_submit_composer_ids(
    *,
    bridge_status: dict[str, object] | None,
    active_composer_id: str | None,
    fallback_composer_id: str | None,
) -> list[str]:
    candidate_ids = _bridge_selected_composer_ids(bridge_status)
    for composer_id in (active_composer_id, fallback_composer_id):
        if composer_id and composer_id not in candidate_ids:
            candidate_ids.append(composer_id)
    return candidate_ids


def _preferred_candidate_submit_composer_id(
    candidate_ids: list[str],
) -> str | None:
    for composer_id in candidate_ids:
        if _composer_has_history(composer_id):
            return composer_id
    return candidate_ids[0] if candidate_ids else None


def _composer_has_history(composer_id: str | None) -> bool:
    marker = _latest_user_marker(composer_id)
    if marker is not None:
        return True
    if not composer_id:
        return False
    try:
        return bool(load_bubbles(composer_id))
    except CursorAppTapError:
        return False
