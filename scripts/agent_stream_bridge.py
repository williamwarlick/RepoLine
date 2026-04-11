#!/usr/bin/env python3
"""Debug a coding CLI text stream as speech-friendly JSONL."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from model_stream import TextStreamConfig, stream_text_events


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a coding CLI's incremental output into speech-friendly JSONL events."
    )
    parser.add_argument("prompt", help="Prompt to send to the configured coding CLI.")
    parser.add_argument(
        "--provider",
        choices=("claude", "codex"),
        default="claude",
        help="Which coding CLI to run.",
    )
    parser.add_argument(
        "--session-id",
        default="00000000-0000-0000-0000-000000000001",
        help="Claude session UUID to reuse for continuity. Claude only.",
    )
    parser.add_argument(
        "--resume-session-id",
        help="Existing provider session/thread id to resume.",
    )
    parser.add_argument(
        "--system-prompt",
        help="Extra spoken-style instructions appended to the provider turn.",
    )
    parser.add_argument(
        "--model",
        help="Optional model alias or full model name.",
    )
    parser.add_argument(
        "--working-directory",
        help="Directory the coding CLI should treat as its working root.",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=140,
        help="Fallback chunk size when punctuation is sparse.",
    )
    args = parser.parse_args()

    config = TextStreamConfig(
        prompt=args.prompt,
        provider=args.provider,
        session_id=args.session_id,
        resume_session_id=args.resume_session_id,
        system_prompt=args.system_prompt,
        model=args.model,
        working_directory=args.working_directory,
        chunk_chars=args.chunk_chars,
    )

    async for event in stream_text_events(config):
        emit(asdict(event))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
