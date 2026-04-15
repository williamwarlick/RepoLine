#!/usr/bin/env python3
"""Submit a prompt into the active Cursor composer for a workspace."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from cursor_app_submit import (  # noqa: E402
    DEFAULT_CURSOR_APP_COMMAND_TITLE,
    DEFAULT_CURSOR_APP_SUBMIT_MODE,
    CursorAppSubmitError,
    submit_prompt_to_cursor_app,
)


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit a prompt into the active Cursor app composer."
    )
    parser.add_argument(
        "--workspace",
        default=str(REPO_ROOT),
        help="Workspace root whose Cursor window should receive the prompt.",
    )
    parser.add_argument(
        "--command-title",
        default=DEFAULT_CURSOR_APP_COMMAND_TITLE,
        help="Command Palette entry used to focus the composer input.",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Prompt text to paste and submit into the Cursor app.",
    )
    parser.add_argument(
        "--submit-mode",
        default=DEFAULT_CURSOR_APP_SUBMIT_MODE,
        help=(
            "Cursor app submit mode: auto, bridge-composer-handle, "
            "bridge-submit, or active-input."
        ),
    )
    args = parser.parse_args()

    try:
        await submit_prompt_to_cursor_app(
            workspace_root=args.workspace,
            prompt=args.prompt,
            command_title=args.command_title,
            submit_mode=args.submit_mode,
        )
    except CursorAppSubmitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
