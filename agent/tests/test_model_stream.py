from model_stream import TextStreamConfig, build_codex_command, normalize_provider


def test_build_codex_command_starts_new_session() -> None:
    config = TextStreamConfig(
        provider="codex",
        prompt="Hello",
        system_prompt="Speak briefly.",
        model="gpt-5-codex",
        working_directory="/tmp/project",
    )

    command = build_codex_command(config)

    assert command[:5] == ["codex", "exec", "--json", "--color", "never"]
    assert "--json" in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--model" in command
    assert "gpt-5-codex" in command
    assert command[-1] == "Speak briefly.\n\nUser request:\nHello"


def test_build_codex_command_can_resume_session() -> None:
    config = TextStreamConfig(
        provider="codex",
        prompt="Follow up",
        resume_session_id="019d7d81-ef86-7671-a691-d46652c8dd7e",
        codex_dangerously_bypass_approvals_and_sandbox=False,
    )

    command = build_codex_command(config)

    assert command[:4] == [
        "codex",
        "exec",
        "resume",
        "--json",
    ]
    assert "--skip-git-repo-check" in command
    assert "--full-auto" in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert command[-2] == "019d7d81-ef86-7671-a691-d46652c8dd7e"
    assert command[-1] == "Follow up"


def test_normalize_provider_defaults_to_claude() -> None:
    assert normalize_provider(None) == "claude"
    assert normalize_provider("CoDeX") == "codex"
