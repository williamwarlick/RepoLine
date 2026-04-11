from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator

from livekit import rtc

SAMPLE_RATE = 24_000
CHANNELS = 1
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
THINKING_CUE_FREQUENCIES = (659.25, 830.61, 987.77)
THINKING_CUE_NOTE_SECONDS = 0.09
THINKING_CUE_GAP_SECONDS = 0.025
THINKING_CUE_VOLUME = 0.11

_WHITESPACE_RE = re.compile(r"\s+")


def build_initial_status_message(user_text: str) -> str:
    normalized = _normalize_text(user_text)
    if not normalized:
        return "I'm checking that now."

    if ".env" in normalized or "environment variable" in normalized or "env var" in normalized:
        return "I'm checking the repo for environment details now."

    if any(
        keyword in normalized
        for keyword in ("file", "files", "folder", "folders", "directory", "directories")
    ):
        return "I'm looking through the repo for that now."

    if any(
        keyword in normalized
        for keyword in ("search", "find", "grep", "look for", "where", "which", "show", "list")
    ):
        return "I'm searching through that now."

    if any(
        keyword in normalized
        for keyword in ("bug", "error", "issue", "failing", "broken", "debug", "trace")
    ):
        return "I'm tracing that through now."

    if any(
        keyword in normalized
        for keyword in ("fix", "change", "update", "edit", "implement", "add", "remove")
    ):
        return "I'm working on that change now."

    if any(keyword in normalized for keyword in ("why", "how", "explain", "walk me through")):
        return "I'm tracing through that now."

    return "I'm checking that now."


async def generate_thinking_cue() -> AsyncIterator[rtc.AudioFrame]:
    for index, frequency in enumerate(THINKING_CUE_FREQUENCIES):
        async for frame in _generate_tone(frequency, THINKING_CUE_NOTE_SECONDS):
            yield frame
        if index < len(THINKING_CUE_FREQUENCIES) - 1:
            async for frame in _generate_silence(THINKING_CUE_GAP_SECONDS):
                yield frame


async def _generate_tone(
    frequency: float,
    duration_seconds: float,
) -> AsyncIterator[rtc.AudioFrame]:
    total_samples = int(SAMPLE_RATE * duration_seconds)

    for start in range(0, total_samples, SAMPLES_PER_FRAME):
        samples = min(SAMPLES_PER_FRAME, total_samples - start)
        frame = rtc.AudioFrame.create(
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
            samples_per_channel=samples,
        )
        data = frame.data

        for offset in range(samples):
            absolute_index = start + offset
            envelope = _amplitude_envelope(absolute_index, total_samples)
            sample = int(
                32767
                * THINKING_CUE_VOLUME
                * envelope
                * math.sin(2 * math.pi * frequency * absolute_index / SAMPLE_RATE)
            )
            data[offset] = sample

        yield frame
        await asyncio.sleep(0)


async def _generate_silence(duration_seconds: float) -> AsyncIterator[rtc.AudioFrame]:
    total_samples = int(SAMPLE_RATE * duration_seconds)
    if total_samples <= 0:
        return

    for start in range(0, total_samples, SAMPLES_PER_FRAME):
        samples = min(SAMPLES_PER_FRAME, total_samples - start)
        yield rtc.AudioFrame.create(
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
            samples_per_channel=samples,
        )
        await asyncio.sleep(0)


def _amplitude_envelope(sample_index: int, total_samples: int) -> float:
    fade_samples = max(1, min(total_samples // 4, int(SAMPLE_RATE * 0.01)))

    if sample_index < fade_samples:
        return sample_index / fade_samples
    if sample_index >= total_samples - fade_samples:
        return max(0.0, (total_samples - sample_index) / fade_samples)
    return 1.0


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().lower()
