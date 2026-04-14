#!/usr/bin/env python3
"""Tail active Cursor app composer output for the current workspace."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from cursor_app_tap import (  # noqa: E402
    CursorAppTapError,
    CursorComposerTail,
    find_active_composer_id,
    update_to_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read active Cursor composer bubbles from the local Cursor SQLite state."
        )
    )
    parser.add_argument(
        "--workspace",
        default=str(REPO_ROOT),
        help="Workspace root to resolve the active Cursor composer from.",
    )
    parser.add_argument(
        "--composer-id",
        help="Optional explicit Cursor composer ID to follow.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Polling interval in seconds while following updates.",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Do not emit the existing conversation snapshot before following.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the current snapshot and exit without following.",
    )
    args = parser.parse_args()

    try:
        composer_id = args.composer_id or find_active_composer_id(args.workspace)
    except CursorAppTapError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "kind": "composer_selected",
                "composer_id": composer_id,
            }
        ),
        flush=True,
    )

    tail = CursorComposerTail(composer_id)
    initial_updates = tail.snapshot_updates(include_existing=not args.no_history)
    for update in initial_updates:
        print(update_to_json(update), flush=True)

    if args.once:
        return 0

    while True:
        for update in tail.snapshot_updates(include_existing=False):
            print(update_to_json(update), flush=True)
        time.sleep(args.poll_interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
