import asyncio

from voice_behavior import (
    CHANNELS,
    SAMPLE_RATE,
    generate_repeating_thinking_cue,
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


def test_generate_repeating_thinking_cue_can_play_once_when_interval_is_zero() -> None:
    async def collect():
        frames = []
        async for frame in generate_repeating_thinking_cue(interval_ms=0):
            frames.append(frame)
        return frames

    frames = asyncio.run(collect())

    assert frames
    assert all(frame.sample_rate == SAMPLE_RATE for frame in frames)
