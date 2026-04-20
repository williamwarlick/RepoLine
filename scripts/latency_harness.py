#!/usr/bin/env python3
"""Run repeatable latency benchmarks for RepoLine provider streams and direct provider CLI commands."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

from latency_harness import (  # noqa: E402
    BenchmarkRunMetadata,
    format_results,
    load_benchmark_plan,
    results_to_jsonl,
    run_benchmark_plan,
    turn_result_to_jsonl_line,
)


def _git_output(*args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    value = proc.stdout.strip()
    return value or None


def _build_run_metadata(scenario_file: str) -> BenchmarkRunMetadata:
    git_sha = _git_output("rev-parse", "HEAD")
    git_sha_short = _git_output("rev-parse", "--short", "HEAD")
    plan_resolved_path = Path(scenario_file).expanduser().resolve()
    plan_path = str(plan_resolved_path)
    plan_sha256 = hashlib.sha256(plan_resolved_path.read_bytes()).hexdigest()
    return BenchmarkRunMetadata(
        run_id=uuid.uuid4().hex,
        plan_path=plan_path,
        plan_sha256=plan_sha256,
        git_sha=git_sha,
        git_sha_short=git_sha_short,
        host_os=platform.system() or None,
        host_arch=platform.machine() or None,
        python_version=platform.python_version() or None,
        started_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    run_metadata = _build_run_metadata(args.scenario_file)
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
        plan,
        run_metadata=run_metadata,
        on_turn_result=_append_turn_result_jsonl_line,
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
