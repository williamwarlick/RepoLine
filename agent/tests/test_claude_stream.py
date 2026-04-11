from claude_stream import (
    ClaudeStreamConfig,
    SentenceChunker,
    build_claude_command,
    extract_text_from_content,
)


def test_sentence_chunker_splits_on_punctuation() -> None:
    chunker = SentenceChunker(chunk_chars=50)

    chunks = chunker.feed("First sentence. Second sentence!")

    assert chunks == ["First sentence.", "Second sentence!"]
    assert chunker.flush() == []


def test_sentence_chunker_falls_back_to_character_budget() -> None:
    chunker = SentenceChunker(chunk_chars=10)

    chunks = chunker.feed("alpha beta gamma delta")

    assert chunks == ["alpha", "beta", "gamma"]
    assert chunker.flush() == ["delta"]


def test_build_claude_command_uses_session_id_and_system_prompt() -> None:
    config = ClaudeStreamConfig(
        prompt="Hello",
        session_id="123e4567-e89b-12d3-a456-426614174000",
        system_prompt="Speak briefly.",
        model="sonnet",
        thinking_level="medium",
        working_directory="/tmp/project",
    )

    command = build_claude_command(config)

    assert "--session-id" in command
    assert "123e4567-e89b-12d3-a456-426614174000" in command
    assert "--append-system-prompt" in command
    assert "Speak briefly." in command
    assert "--model" in command
    assert "sonnet" in command
    assert "--effort" in command
    assert "medium" in command


def test_build_claude_command_can_resume_and_fork() -> None:
    config = ClaudeStreamConfig(
        prompt="Follow up",
        session_id="22222222-2222-2222-2222-222222222222",
        resume_session_id="11111111-1111-1111-1111-111111111111",
    )

    command = build_claude_command(config)

    assert "--resume" in command
    assert "11111111-1111-1111-1111-111111111111" in command
    assert "--fork-session" in command
    assert "--session-id" in command
    assert "22222222-2222-2222-2222-222222222222" in command


def test_extract_text_from_content_ignores_non_text_blocks() -> None:
    content = [
        {"type": "thinking", "thinking": "internal"},
        {"type": "text", "text": "First sentence."},
        {"type": "text", "text": "Second sentence."},
    ]

    assert extract_text_from_content(content) == "First sentence. Second sentence."
