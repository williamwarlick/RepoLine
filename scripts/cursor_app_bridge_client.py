#!/usr/bin/env python3
"""Query the RepoLine Cursor app bridge extension."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from cursor_app_bridge_client import (  # noqa: E402
    CursorAppBridgeError,
    ping_cursor_app_bridge,
    request_cursor_app_bridge,
    submit_prompt_via_cursor_app_bridge,
)


async def _run(args: argparse.Namespace) -> int:
    if args.method == "ping":
        payload = await ping_cursor_app_bridge(args.workspace)
        if payload is None:
            print("error: bridge state file was not found", file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2))
        return 0

    if args.method == "exec":
        payload = await request_cursor_app_bridge(
            workspace_root=args.workspace,
            payload={
                "method": "exec",
                "command": args.command,
                "args": args.args,
            },
        )
        if payload is None:
            print("error: bridge state file was not found", file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2))
        return 0

    if args.method in {"submitOpenAndSend", "submitFollowupAndSend"}:
        payload = await request_cursor_app_bridge(
            workspace_root=args.workspace,
            payload={
                "method": args.method,
                "prompt": args.prompt,
            },
        )
        if payload is None:
            print("error: bridge state file was not found", file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2))
        return 0

    try:
        result = await submit_prompt_via_cursor_app_bridge(
            workspace_root=args.workspace,
            prompt=args.prompt,
            composer_id=args.composer_id,
        )
    except CursorAppBridgeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if result is None:
        print("error: bridge state file was not found", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "composer_id": result.composer_id,
                "via": result.via,
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        default=str(REPO_ROOT),
        help="Workspace root for the target Cursor window.",
    )
    parser.add_argument(
        "--method",
        choices=(
            "ping",
            "submit",
            "exec",
            "submitOpenAndSend",
            "submitFollowupAndSend",
        ),
        default="ping",
        help="Bridge action to perform.",
    )
    parser.add_argument(
        "--prompt",
        help="Prompt text to submit when --method submit is used.",
    )
    parser.add_argument(
        "--composer-id",
        help="Optional explicit composer ID to target.",
    )
    parser.add_argument(
        "--command",
        help="Command name to execute when --method exec is used.",
    )
    parser.add_argument(
        "--arg",
        dest="args",
        action="append",
        default=[],
        help="JSON argument value for --method exec. Repeat for multiple args.",
    )
    args = parser.parse_args()

    if args.method == "submit" and not args.prompt:
        parser.error("--prompt is required when --method submit is used.")
    if args.method in {"submitOpenAndSend", "submitFollowupAndSend"} and not args.prompt:
        parser.error("--prompt is required for the selected submit method.")
    if args.method == "exec" and not args.command:
        parser.error("--command is required when --method exec is used.")

    if args.method == "exec":
        parsed_args = []
        for raw_arg in args.args:
            try:
                parsed_args.append(json.loads(raw_arg))
            except json.JSONDecodeError:
                parsed_args.append(raw_arg)
        args.args = parsed_args

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
