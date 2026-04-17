from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from livekit import rtc

SAMPLE_RATE = 24_000
CHANNELS = 1
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
DEFAULT_THINKING_CUE_PRESET = "soft-pulse"
DEFAULT_THINKING_CUE_INTERVAL_MS = 1800
DEFAULT_THINKING_CUE_VOLUME = 0.11
MAX_THINKING_CUE_INTERVAL_MS = 10_000
ThinkingCuePreset = Literal["off", "soft-pulse", "glass"]
THINKING_CUE_PRESETS: tuple[ThinkingCuePreset, ...] = ("off", "soft-pulse", "glass")


@dataclass(frozen=True, slots=True)
class ThinkingCueNote:
    frequency: float
    duration_seconds: float
    gain: float
    gap_after_seconds: float = 0.0


THINKING_CUE_DEFINITIONS: dict[ThinkingCuePreset, tuple[ThinkingCueNote, ...]] = {
    "off": (),
    "soft-pulse": (
        ThinkingCueNote(
            frequency=659.25,
            duration_seconds=0.09,
            gain=1.0,
            gap_after_seconds=0.025,
        ),
        ThinkingCueNote(
            frequency=830.61,
            duration_seconds=0.09,
            gain=0.82,
            gap_after_seconds=0.025,
        ),
        ThinkingCueNote(
            frequency=987.77,
            duration_seconds=0.09,
            gain=0.7,
        ),
    ),
    "glass": (
        ThinkingCueNote(
            frequency=783.99,
            duration_seconds=0.12,
            gain=0.82,
            gap_after_seconds=0.06,
        ),
        ThinkingCueNote(
            frequency=1174.66,
            duration_seconds=0.18,
            gain=0.56,
        ),
    ),
}


def resolve_thinking_cue_preset(
    value: str | None,
    fallback: ThinkingCuePreset = "off",
) -> ThinkingCuePreset:
    normalized = (value or "").strip().lower().replace("_", "-")
    if not normalized:
        return fallback
    if normalized in THINKING_CUE_PRESETS:
        return normalized  # type: ignore[return-value]
    return fallback


def clamp_thinking_cue_volume(
    value: float | None,
    fallback: float = DEFAULT_THINKING_CUE_VOLUME,
) -> float:
    if value is None or not math.isfinite(value):
        return fallback
    return min(1.0, max(0.0, value))


def clamp_thinking_cue_interval_ms(
    value: int | float | None,
    fallback: int = DEFAULT_THINKING_CUE_INTERVAL_MS,
) -> int:
    if value is None:
        return fallback
    numeric = float(value)
    if not math.isfinite(numeric):
        return fallback
    return round(min(MAX_THINKING_CUE_INTERVAL_MS, max(0.0, numeric)))


def is_thinking_cue_enabled(preset: ThinkingCuePreset) -> bool:
    return preset != "off"


async def generate_thinking_cue(
    *,
    preset: ThinkingCuePreset = DEFAULT_THINKING_CUE_PRESET,
    volume: float = DEFAULT_THINKING_CUE_VOLUME,
) -> AsyncIterator[rtc.AudioFrame]:
    definition = THINKING_CUE_DEFINITIONS[preset]
    normalized_volume = clamp_thinking_cue_volume(volume)
    if not definition or normalized_volume <= 0:
        return

    for note in definition:
        async for frame in _generate_tone(
            note.frequency,
            note.duration_seconds,
            gain=note.gain * normalized_volume,
        ):
            yield frame
        if note.gap_after_seconds > 0:
            async for frame in _generate_silence(note.gap_after_seconds):
                yield frame


async def generate_repeating_thinking_cue(
    *,
    preset: ThinkingCuePreset = DEFAULT_THINKING_CUE_PRESET,
    volume: float = DEFAULT_THINKING_CUE_VOLUME,
    interval_ms: int = DEFAULT_THINKING_CUE_INTERVAL_MS,
) -> AsyncIterator[rtc.AudioFrame]:
    normalized_preset = resolve_thinking_cue_preset(preset, DEFAULT_THINKING_CUE_PRESET)
    if not is_thinking_cue_enabled(normalized_preset):
        return

    normalized_interval_ms = clamp_thinking_cue_interval_ms(interval_ms)
    while True:
        async for frame in generate_thinking_cue(
            preset=normalized_preset,
            volume=volume,
        ):
            yield frame

        if normalized_interval_ms <= 0:
            return

        async for frame in _generate_silence(normalized_interval_ms / 1000):
            yield frame


async def _generate_tone(
    frequency: float,
    duration_seconds: float,
    *,
    gain: float,
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
                * gain
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
