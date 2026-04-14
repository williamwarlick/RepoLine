from cursor_app_submit import (
    BRIDGE_SUBMIT_METHODS,
    DEFAULT_CURSOR_APP_COMMAND_TITLE,
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


def test_bridge_submit_methods_avoid_detached_thread_fallbacks() -> None:
    assert "submitOpenDetachedAndSend" not in BRIDGE_SUBMIT_METHODS
    assert "submitTestOpenDetachedAndSend" not in BRIDGE_SUBMIT_METHODS
    assert "submit" not in BRIDGE_SUBMIT_METHODS
