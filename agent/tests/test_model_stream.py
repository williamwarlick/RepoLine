import pytest

from model_stream import (
    TextStreamConfig,
    _extract_codex_item_artifacts,
    _extract_content_artifacts,
    _extract_embedded_code_artifacts,
    _extract_incremental_text,
    build_claude_command,
    build_codex_command,
    build_cursor_command,
    build_gemini_command,
    infer_access_policy,
    normalize_provider,
)


def test_build_claude_command_uses_readonly_policy() -> None:
    config = TextStreamConfig(
        provider="claude",
        prompt="Hello",
        session_id="123e4567-e89b-12d3-a456-426614174000",
        system_prompt="Speak briefly.",
        access_policy="readonly",
    )

    command = build_claude_command(config)

    assert "--permission-mode" in command
    assert "plan" in command
    assert "--dangerously-skip-permissions" not in command
    assert "--append-system-prompt" in command


def test_build_claude_command_uses_owner_policy() -> None:
    config = TextStreamConfig(
        provider="claude",
        prompt="Hello",
        session_id="123e4567-e89b-12d3-a456-426614174000",
        access_policy="owner",
    )

    command = build_claude_command(config)

    assert "--dangerously-skip-permissions" in command
    assert "--permission-mode" not in command


def test_build_codex_command_starts_new_session_in_readonly_mode() -> None:
    config = TextStreamConfig(
        provider="codex",
        prompt="Hello",
        system_prompt="Speak briefly.",
        model="gpt-5-codex",
        working_directory="/tmp/project",
        thinking_level="low",
        access_policy="readonly",
    )

    command = build_codex_command(config)

    assert command[:5] == ["codex", "exec", "--json", "--color", "never"]
    assert "--json" in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "-c" in command
    assert 'model_reasoning_effort="low"' in command
    assert "--model" in command
    assert "gpt-5-codex" in command
    assert command[-1] == "Speak briefly.\n\nUser request:\nHello"


def test_build_codex_command_can_resume_session() -> None:
    config = TextStreamConfig(
        provider="codex",
        prompt="Follow up",
        resume_session_id="019d7d81-ef86-7671-a691-d46652c8dd7e",
        access_policy="readonly",
    )

    command = build_codex_command(config)

    assert command[:4] == [
        "codex",
        "exec",
        "resume",
        "--json",
    ]
    assert "--skip-git-repo-check" in command
    assert "--sandbox" not in command
    assert "-c" in command
    assert 'sandbox_mode="read-only"' in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert command[-2] == "019d7d81-ef86-7671-a691-d46652c8dd7e"
    assert command[-1] == "Follow up"


def test_build_codex_command_can_resume_workspace_write_session() -> None:
    config = TextStreamConfig(
        provider="codex",
        prompt="Follow up",
        resume_session_id="019d7d81-ef86-7671-a691-d46652c8dd7e",
        access_policy="workspace-write",
    )

    command = build_codex_command(config)

    assert "--full-auto" in command
    assert "--sandbox" not in command


def test_build_cursor_command_enables_headless_force_mode() -> None:
    config = TextStreamConfig(
        provider="cursor",
        prompt="Hello",
        system_prompt="Speak briefly.",
        model="composer-2",
        thinking_level="medium",
        access_policy="owner",
    )

    command = build_cursor_command(config)

    assert command[:4] == ["cursor-agent", "-p", "--output-format", "stream-json"]
    assert "--trust" in command
    assert "--stream-partial-output" in command
    assert "-f" in command
    assert "--approve-mcps" in command
    assert "--sandbox" in command
    assert "disabled" in command
    assert "--model" in command
    assert "composer-2" in command
    assert "Speak briefly." in command[-1]
    assert "medium thinking effort" in command[-1]


def test_build_cursor_command_defaults_to_composer_2_fast() -> None:
    config = TextStreamConfig(
        provider="cursor",
        prompt="Hello",
        access_policy="readonly",
    )

    command = build_cursor_command(config)

    assert "--model" in command
    assert "composer-2-fast" in command
    assert "--trust" in command
    assert "--mode" not in command
    assert "readonly mode" in command[-1]
    assert command[-1].endswith("User request:\nHello")


def test_build_cursor_command_can_resume_session() -> None:
    config = TextStreamConfig(
        provider="cursor",
        prompt="Follow up",
        resume_session_id="cursor-chat-123",
        access_policy="readonly",
    )

    command = build_cursor_command(config)

    assert "--mode" not in command
    assert "--resume" in command
    assert "cursor-chat-123" in command
    assert "-f" not in command
    assert "--approve-mcps" not in command
    assert "--sandbox" in command
    assert "enabled" in command
    assert "--trust" in command
    assert "--stream-partial-output" in command
    assert "readonly mode" in command[-1]
    assert command[-1].endswith("User request:\nFollow up")


def test_build_cursor_command_supports_app_transport() -> None:
    config = TextStreamConfig(
        provider="cursor",
        provider_transport="app",
        provider_submit_mode="bridge-composer-handle",
        prompt="Follow up",
        working_directory="/tmp/repo",
    )

    command = build_cursor_command(config)

    assert command[1].endswith("scripts/cursor_app_submit.py")
    assert "--workspace" in command
    assert any(value.endswith("/tmp/repo") for value in command)
    assert "--prompt" in command
    assert any(value.endswith("Follow up") for value in command)
    assert "--submit-mode" in command
    assert "bridge-composer-handle" in command


def test_build_gemini_command_defaults_to_flash_and_plan_mode() -> None:
    config = TextStreamConfig(
        provider="gemini",
        prompt="Hello",
        system_prompt="Speak briefly.",
        access_policy="readonly",
    )

    command = build_gemini_command(config)

    assert command[:4] == ["gemini", "--output-format", "stream-json", "-p"]
    assert "--approval-mode" in command
    assert "plan" in command
    assert "--sandbox" in command
    assert "--model" in command
    assert "gemini-2.5-flash" in command
    assert command[-1] == "gemini-2.5-flash"
    assert "Speak briefly." in command[4]


def test_build_gemini_command_can_resume_in_owner_mode() -> None:
    config = TextStreamConfig(
        provider="gemini",
        prompt="Follow up",
        resume_session_id="gemini-session-123",
        model="gemini-3-flash-preview",
        access_policy="owner",
    )

    command = build_gemini_command(config)

    assert "--resume" in command
    assert "gemini-session-123" in command
    assert "--yolo" in command
    assert "--sandbox" not in command
    assert command[-1] == "gemini-3-flash-preview"


def test_build_gemini_command_rejects_non_cli_transport() -> None:
    config = TextStreamConfig(
        provider="gemini",
        provider_transport="app",
        prompt="Follow up",
        model="gemini-2.5-flash",
        thinking_level="low",
    )

    with pytest.raises(ValueError, match="Gemini only supports the Gemini CLI transport"):
        build_gemini_command(config)


def test_normalize_provider_defaults_to_claude() -> None:
    assert normalize_provider(None) == "claude"
    assert normalize_provider("CoDeX") == "codex"
    assert normalize_provider("cursor-agent") == "cursor"
    assert normalize_provider("gemini") == "gemini"


def test_infer_access_policy_prefers_explicit_setting() -> None:
    assert infer_access_policy("codex", "owner") == "owner"
    assert infer_access_policy("claude", "write") == "workspace-write"


def test_infer_access_policy_uses_legacy_codex_flag() -> None:
    assert infer_access_policy("codex", legacy_codex_bypass=True) == "owner"
    assert infer_access_policy("codex", legacy_codex_bypass=False) == "workspace-write"


def test_infer_access_policy_uses_legacy_cursor_flags() -> None:
    assert (
        infer_access_policy("cursor", legacy_cursor_sandbox_mode="disabled") == "owner"
    )
    assert (
        infer_access_policy("cursor", legacy_cursor_sandbox_mode="enabled")
        == "workspace-write"
    )


def test_extract_content_artifacts_supports_claude_tool_blocks() -> None:
    artifacts = _extract_content_artifacts(
        provider="claude",
        content=[
            {
                "id": "toolu_123",
                "type": "tool_use",
                "name": "exec_command",
                "input": {"command": ["pwd"]},
            }
        ],
        seen_artifact_ids=set(),
    )

    assert len(artifacts) == 1
    assert artifacts[0].kind == "tool"
    assert artifacts[0].title == "exec_command"
    assert artifacts[0].text == "pwd"
    assert artifacts[0].language == "bash"


def test_extract_codex_item_artifacts_supports_tool_calls() -> None:
    artifacts = _extract_codex_item_artifacts(
        {
            "id": "item_123",
            "type": "exec_command",
            "command": ["git", "status", "--short"],
        }
    )

    assert len(artifacts) == 1
    assert artifacts[0].kind == "tool"
    assert artifacts[0].title == "Exec Command"
    assert artifacts[0].text == "git status --short"
    assert artifacts[0].language == "bash"


def test_extract_embedded_code_artifacts_supports_code_and_diffs() -> None:
    artifacts = _extract_embedded_code_artifacts(
        """
Here is a diff:

```diff
diff --git a/foo.py b/foo.py
+print("hello")
```

And a helper:

```python
def greet() -> None:
    print("hello")
```
""".strip()
    )

    assert [artifact.kind for artifact in artifacts] == ["diff", "code"]
    assert artifacts[0].language == "diff"
    assert artifacts[1].language == "python"


def test_extract_incremental_text_ignores_whitespace_only_cursor_replays() -> None:
    assert (
        _extract_incremental_text(
            "I found the issue.\n\nIt is in the Cursor result handler.",
            "I found the issue. It is in the Cursor result handler.",
        )
        is None
    )


def test_extract_incremental_text_preserves_new_suffix_after_whitespace_reformat() -> None:
    assert (
        _extract_incremental_text(
            "I found the issue.\n\nIt is in the Cursor result handler. I am patching it now.",
            "I found the issue. It is in the Cursor result handler.",
        )
        == "I am patching it now."
    )
