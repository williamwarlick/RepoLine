#!/usr/bin/env python3
"""Debug Claude Code's partial-output stream as speech-friendly JSONL."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from claude_stream import ClaudeStreamConfig, stream_claude_events


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn Claude Code's incremental output into speech-friendly JSONL events."
    )
    parser.add_argument("prompt", help="Prompt to send to Claude Code.")
    parser.add_argument(
        "--session-id",
        default="00000000-0000-0000-0000-000000000001",
        help="Claude Code session UUID to reuse for continuity.",
    )
    parser.add_argument(
        "--system-prompt",
        help="Extra spoken-style instructions appended to Claude Code.",
    )
    parser.add_argument(
        "--model",
        help="Optional Claude model alias or full model name.",
    )
    parser.add_argument(
        "--working-directory",
        help="Directory Claude Code should treat as its working root.",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=140,
        help="Fallback chunk size when punctuation is sparse.",
    )
    args = parser.parse_args()

    config = ClaudeStreamConfig(
        prompt=args.prompt,
        session_id=args.session_id,
        system_prompt=args.system_prompt,
        model=args.model,
        working_directory=args.working_directory,
        chunk_chars=args.chunk_chars,
    )

    async for event in stream_claude_events(config):
        emit(asdict(event))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
