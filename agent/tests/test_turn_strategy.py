from turn_strategy import (
    count_transcript_words,
    join_transcript_parts,
    resolve_pending_turn_delay_seconds,
)


def test_join_transcript_parts_skips_blank_segments() -> None:
    assert join_transcript_parts(["Try", "  ", "using the Grill Me skill"]) == (
        "Try using the Grill Me skill"
    )


def test_count_transcript_words_handles_punctuation() -> None:
    assert count_transcript_words("What did I just say?") == 5
    assert count_transcript_words("Hello?") == 1


def test_resolve_pending_turn_delay_uses_short_grace_for_brief_turns() -> None:
    assert (
        resolve_pending_turn_delay_seconds(
            ["Try"],
            base_delay_seconds=0.85,
            short_transcript_delay_seconds=2.75,
            short_transcript_word_threshold=2,
        )
        == 2.75
    )


def test_resolve_pending_turn_delay_uses_base_delay_for_longer_turns() -> None:
    assert (
        resolve_pending_turn_delay_seconds(
            ["What did you find about using the GrowMe scale?"],
            base_delay_seconds=0.85,
            short_transcript_delay_seconds=2.75,
            short_transcript_word_threshold=2,
        )
        == 0.85
    )
