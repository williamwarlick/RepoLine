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
    results_to_jsonl,
    run_benchmark_plan,
    turn_result_to_jsonl_line,
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
        help="Optional path to write normalized JSONL turn records.",
    )
    args = parser.parse_args()

    plan = load_benchmark_plan(args.scenario_file, working_directory=REPO_ROOT)
    json_output_path: Path | None = None
    if args.json_out:
        json_output_path = Path(args.json_out).expanduser()
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text("", encoding="utf-8")

    def _append_turn_result_jsonl_line(result) -> None:
        if json_output_path is None:
            return
        with json_output_path.open("a", encoding="utf-8") as handle:
            handle.write(turn_result_to_jsonl_line(result))
            handle.write("\n")

    results = await run_benchmark_plan(
        plan, on_turn_result=_append_turn_result_jsonl_line
    )
    print(format_results(results))

    if json_output_path is not None:
        expected_jsonl = results_to_jsonl(results)
        actual_jsonl = json_output_path.read_text(encoding="utf-8").rstrip("\n")
        if actual_jsonl != expected_jsonl:
            json_output_path.write_text(expected_jsonl + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
