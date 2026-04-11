from __future__ import annotations

import re
from collections.abc import Sequence

_WORD_RE = re.compile(r"\b[\w'-]+\b")


def join_transcript_parts(parts: Sequence[str]) -> str:
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def count_transcript_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def resolve_pending_turn_delay_seconds(
    parts: Sequence[str],
    *,
    base_delay_seconds: float,
    short_transcript_delay_seconds: float,
    short_transcript_word_threshold: int,
) -> float:
    text = join_transcript_parts(parts)
    if not text:
        return base_delay_seconds

    if count_transcript_words(text) <= short_transcript_word_threshold:
        return max(base_delay_seconds, short_transcript_delay_seconds)

    return base_delay_seconds
