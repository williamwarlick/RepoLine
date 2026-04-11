import asyncio

from voice_behavior import (
    CHANNELS,
    SAMPLE_RATE,
    build_followup_status_message,
    build_initial_status_message,
    generate_thinking_cue,
)


def test_generate_thinking_cue_emits_audio_frames() -> None:
    async def collect():
        frames = []
        async for frame in generate_thinking_cue():
            frames.append(frame)
        return frames

    frames = asyncio.run(collect())

    assert frames
    assert all(frame.sample_rate == SAMPLE_RATE for frame in frames)
    assert all(frame.num_channels == CHANNELS for frame in frames)


def test_build_initial_status_message_mentions_repo_search() -> None:
    message = build_initial_status_message(
        "Can you tell me which folders have .env files?"
    )

    assert message == "I'm checking the repo for environment details now."


def test_build_initial_status_message_mentions_debugging() -> None:
    message = build_initial_status_message("Why is this failing with an error?")

    assert message == "I'm tracing that through now."


def test_build_followup_status_message_mentions_repo_search() -> None:
    message = build_followup_status_message(
        "Can you tell me which folders have .env files?"
    )

    assert message == "I'm checking the repo for the environment details now."


def test_build_followup_status_message_mentions_change_work() -> None:
    message = build_followup_status_message("Can you update the onboarding flow?")

    assert message == "I'm getting into the code for that change now."


def test_build_followup_status_message_rotates_phrases() -> None:
    first = build_followup_status_message("Can you update the onboarding flow?", 0)
    second = build_followup_status_message("Can you update the onboarding flow?", 1)
    third = build_followup_status_message("Can you update the onboarding flow?", 2)

    assert first == "I'm getting into the code for that change now."
    assert second == "I'm still tracing what needs to change before I touch it."
    assert third == "I'm narrowing down the affected files now."
