from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from cursor_app_bridge_client import (
    CursorAppBridgeError,
    request_cursor_app_bridge,
    submit_prompt_via_cursor_app_bridge,
)
from cursor_app_tap import CursorAppTapError, find_active_composer_id, load_bubbles

DEFAULT_CURSOR_APP_COMMAND_TITLE = "Focus Chat Followup"
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
FALLBACK_SUBMIT_VERIFICATION_TIMEOUT_SECONDS = 1.8
SUBMIT_VERIFICATION_POLL_INTERVAL_SECONDS = 0.05
BRIDGE_SUBMIT_VERIFICATION_TIMEOUT_SECONDS = 1.35
BRIDGE_SUBMIT_METHODS = (
    "submitFollowupClipboardAndSend",
    "submitFollowupAndSend",
    "submitStartPromptClipboardAndSend",
)


@dataclass(frozen=True, slots=True)
class CursorAppSubmitResult:
    composer_id: str


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
) -> CursorAppSubmitResult:
    workspace_path = str(Path(workspace_root).expanduser().resolve())
    composer_id = _safe_find_active_composer_id(workspace_path)

    baseline_text_by_composer = _baseline_latest_user_texts(composer_id)
    active_submit_result = await _try_bridge_followup_active_submit(
        workspace_root=workspace_path,
        prompt=prompt,
        baseline_text_by_composer=baseline_text_by_composer,
        composer_id=composer_id,
    )
    if active_submit_result is not None:
        return active_submit_result

    bridge_errors: list[str] = []
    for bridge_method in BRIDGE_SUBMIT_METHODS:
        try:
            bridge_result = await submit_prompt_via_cursor_app_bridge(
                workspace_root=workspace_path,
                prompt=prompt,
                composer_id=composer_id,
                method=bridge_method,
            )
        except CursorAppBridgeError as exc:
            bridge_errors.append(str(exc))
            continue
        if bridge_result is None:
            break

        verified_result = await _wait_for_submitted_prompt(
            workspace_root=workspace_path,
            prompt=prompt,
            baseline_text_by_composer=baseline_text_by_composer,
            fallback_composer_id=bridge_result.composer_id or composer_id,
            timeout_seconds=BRIDGE_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
        )
        if verified_result is not None:
            return verified_result

    shortcut_error = await _run_shortcut_osascript(prompt=prompt)
    if shortcut_error is None:
        shortcut_result = await _wait_for_submitted_prompt(
            workspace_root=workspace_path,
            prompt=prompt,
            baseline_text_by_composer=baseline_text_by_composer,
            fallback_composer_id=composer_id,
            timeout_seconds=FAST_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
        )
        if shortcut_result is not None:
            return shortcut_result

    first_error = await _run_submit_osascript(
        prompt=prompt,
        command_title=command_title,
    )
    if first_error is None:
        verified_result = await _wait_for_submitted_prompt(
            workspace_root=workspace_path,
            prompt=prompt,
            baseline_text_by_composer=baseline_text_by_composer,
            fallback_composer_id=composer_id,
            timeout_seconds=FALLBACK_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
        )
        if verified_result is not None:
            return verified_result

    focus_proc = await asyncio.create_subprocess_exec(
        "cursor",
        "-r",
        workspace_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, focus_stderr = await focus_proc.communicate()
    if focus_proc.returncode not in {0, None}:
        message = focus_stderr.decode("utf-8", errors="replace").strip()
        raise CursorAppSubmitError(
            message or f"Failed to focus Cursor workspace: {workspace_path}"
        )

    await asyncio.sleep(WORKSPACE_REFocus_DELAY_SECONDS)

    second_error = await _run_submit_osascript(
        prompt=prompt,
        command_title=command_title,
        activate_delay_seconds=FALLBACK_ACTIVATE_DELAY_SECONDS,
        palette_type_delay_seconds=FALLBACK_PALETTE_TYPE_DELAY_SECONDS,
        command_confirm_delay_seconds=FALLBACK_COMMAND_CONFIRM_DELAY_SECONDS,
        paste_delay_seconds=FALLBACK_PASTE_DELAY_SECONDS,
        submit_delay_seconds=FALLBACK_SUBMIT_DELAY_SECONDS,
    )
    if second_error is not None:
        bridge_error = bridge_errors[-1] if bridge_errors else None
        raise CursorAppSubmitError(
            second_error or first_error or shortcut_error or bridge_error
        )

    verified_result = await _wait_for_submitted_prompt(
        workspace_root=workspace_path,
        prompt=prompt,
        baseline_text_by_composer=baseline_text_by_composer,
        fallback_composer_id=composer_id,
        timeout_seconds=FALLBACK_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
    )
    if verified_result is not None:
        return verified_result

    raise CursorAppSubmitError(
        "Cursor app accepted the submit command, but RepoLine could not verify the prompt landed in composer state."
    )


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


def _latest_user_text(composer_id: str | None) -> str | None:
    if not composer_id:
        return None
    try:
        bubbles = load_bubbles(composer_id)
    except CursorAppTapError:
        return None
    for bubble in reversed(bubbles):
        if bubble.role == "user" and bubble.text.strip():
            return bubble.text.strip()
    return None


async def _try_bridge_followup_active_submit(
    *,
    workspace_root: str,
    prompt: str,
    baseline_text_by_composer: dict[str, str | None],
    composer_id: str | None,
) -> CursorAppSubmitResult | None:
    try:
        bridge_state = await request_cursor_app_bridge(
            workspace_root=workspace_root,
            payload={"method": "exec", "command": "composer.focusComposer", "args": []},
        )
    except CursorAppBridgeError:
        return None
    if bridge_state is None:
        return None

    try:
        await request_cursor_app_bridge(
            workspace_root=workspace_root,
            payload={
                "method": "exec",
                "command": "aichat.newfollowupaction",
                "args": [],
            },
        )
    except CursorAppBridgeError:
        return None

    active_submit_error = await _run_active_input_osascript(prompt=prompt)
    if active_submit_error is not None:
        return None

    verified_result = await _wait_for_submitted_prompt(
        workspace_root=workspace_root,
        prompt=prompt,
        baseline_text_by_composer=baseline_text_by_composer,
        fallback_composer_id=_safe_find_active_composer_id(workspace_root)
        or composer_id,
        timeout_seconds=FALLBACK_SUBMIT_VERIFICATION_TIMEOUT_SECONDS,
    )
    return verified_result


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


def _baseline_latest_user_texts(composer_id: str | None) -> dict[str, str | None]:
    if not composer_id:
        return {}
    return {composer_id: _latest_user_text(composer_id)}


async def _wait_for_submitted_prompt(
    *,
    workspace_root: str,
    prompt: str,
    baseline_text_by_composer: dict[str, str | None],
    fallback_composer_id: str | None,
    timeout_seconds: float,
) -> CursorAppSubmitResult | None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    normalized_prompt = prompt.strip()

    while asyncio.get_running_loop().time() < deadline:
        active_composer_id = _safe_find_active_composer_id(workspace_root)
        candidate_ids: list[str] = []
        for composer_id in (active_composer_id, fallback_composer_id):
            if composer_id and composer_id not in candidate_ids:
                candidate_ids.append(composer_id)

        for composer_id in candidate_ids:
            latest_user_text = _latest_user_text(composer_id)
            if latest_user_text is None:
                continue
            if latest_user_text != normalized_prompt:
                continue
            if baseline_text_by_composer.get(composer_id) == latest_user_text:
                continue
            return CursorAppSubmitResult(composer_id=composer_id)

        await asyncio.sleep(SUBMIT_VERIFICATION_POLL_INTERVAL_SECONDS)

    return None
