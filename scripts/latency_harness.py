#!/usr/bin/env python3
"""Run repeatable latency benchmarks for RepoLine provider streams and direct provider CLI commands."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from latency_harness import (  # noqa: E402
    format_results,
    load_benchmark_plan,
    results_to_json,
    run_benchmark_plan,
)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark RepoLine latency across provider-stream and raw provider command scenarios."
    )
    parser.add_argument(
        "scenario_file",
        help="Path to a JSON benchmark plan.",
    )
    parser.add_argument(
        "--json-out",
        help="Optional path to write structured JSON results.",
    )
    args = parser.parse_args()

    plan = load_benchmark_plan(args.scenario_file, working_directory=REPO_ROOT)
    results = await run_benchmark_plan(plan)
    print(format_results(results))

    if args.json_out:
        output_path = Path(args.json_out).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(results_to_json(results) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
