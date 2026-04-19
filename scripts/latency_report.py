#!/usr/bin/env python3
"""Render a Markdown benchmark report from RepoLine latency harness JSON output."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 1)

    lower_value = ordered[lower]
    upper_value = ordered[upper]
    fraction = position - lower
    return round(lower_value + (upper_value - lower_value) * fraction, 1)


def _ms_to_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value / 1000:.2f}s"


def _truncate_label(value: str, *, limit: int = 24) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _scenario_label(scenario: dict[str, Any]) -> str:
    return scenario.get("variant") or scenario.get("name") or "scenario"


def _scenario_task(scenario: dict[str, Any]) -> str:
    return scenario.get("task") or scenario.get("name") or "task"


def _turn_text(turn: dict[str, Any]) -> str:
    for key in (
        "response_text",
        "first_response_preview",
        "first_speech_chunk_preview",
        "first_assistant_preview",
    ):
        value = turn.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _turn_succeeded(turn: dict[str, Any]) -> bool:
    return (
        turn.get("exit_code") == 0
        and not turn.get("error_message")
        and bool(_normalize_text(_turn_text(turn)))
    )


def _turn_eval_passed(turn: dict[str, Any], scenario: dict[str, Any]) -> bool | None:
    expected_exact = scenario.get("expected_exact")
    expected_includes = scenario.get("expected_includes") or []

    if not expected_exact and not expected_includes:
        return None
    if not _turn_succeeded(turn):
        return False

    response_text = _normalize_text(_turn_text(turn))
    if expected_exact and response_text != _normalize_text(expected_exact):
        return False

    for fragment in expected_includes:
        if _normalize_text(fragment) not in response_text:
            return False

    return True


def _bar_chart(title: str, labels: list[str], seconds: list[float]) -> str | None:
    if not labels or not seconds:
        return None

    ceiling = max(seconds)
    rounded_ceiling = max(1, math.ceil(ceiling + 0.25))
    label_list = ", ".join(json.dumps(_truncate_label(label)) for label in labels)
    value_list = ", ".join(f"{value:.2f}" for value in seconds)

    return "\n".join(
        [
            "```mermaid",
            "xychart-beta",
            f"    title {json.dumps(title)}",
            f"    x-axis [{label_list}]",
            f'    y-axis "Seconds" 0 --> {rounded_ceiling}',
            f"    bar [{value_list}]",
            "```",
        ]
    )


def _render_report(results: list[dict[str, Any]], *, source_path: Path) -> str:
    rows: list[dict[str, Any]] = []
    charts_by_task: dict[str, list[dict[str, Any]]] = {}

    for entry in results:
        scenario = entry.get("scenario", {})
        turns = entry.get("turns", [])
        if not isinstance(scenario, dict) or not isinstance(turns, list):
            continue

        succeeded = [turn for turn in turns if isinstance(turn, dict) and _turn_succeeded(turn)]
        response_values = [
            float(turn["first_response_ms"])
            for turn in succeeded
            if turn.get("first_response_ms") is not None
        ]
        done_values = [
            float(turn["completed_ms"])
            for turn in succeeded
            if turn.get("completed_ms") is not None
        ]

        eval_results = [
            result
            for result in (
                _turn_eval_passed(turn, scenario)
                for turn in turns
                if isinstance(turn, dict)
            )
            if result is not None
        ]

        mean_first_response_ms = round(mean(response_values), 1) if response_values else None
        row = {
            "task": _scenario_task(scenario),
            "label": _scenario_label(scenario),
            "scenario_name": scenario.get("name") or "-",
            "turn_count": len(turns),
            "success_rate": round((len(succeeded) / len(turns)) * 100, 1) if turns else 0.0,
            "eval_rate": (
                round((sum(1 for result in eval_results if result) / len(eval_results)) * 100, 1)
                if eval_results
                else None
            ),
            "mean_first_response_ms": mean_first_response_ms,
            "p50_first_response_ms": _percentile(response_values, 0.5),
            "p90_first_response_ms": _percentile(response_values, 0.9),
            "mean_completed_ms": round(mean(done_values), 1) if done_values else None,
            "notes": [],
        }

        if not succeeded:
            row["notes"].append("no successful turns")
        elif len(succeeded) != len(turns):
            row["notes"].append("partial failures")

        if row["eval_rate"] is None and (
            scenario.get("expected_exact") or scenario.get("expected_includes")
        ):
            row["notes"].append("no graded turns passed")

        rows.append(row)
        if mean_first_response_ms is not None:
            charts_by_task.setdefault(row["task"], []).append(row)

    rows.sort(key=lambda row: (row["task"], row["mean_first_response_ms"] or float("inf"), row["label"]))

    lines = [
        "# RepoLine Benchmark Report",
        "",
        f"Source: `{source_path}`",
        f"Generated: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`",
        "",
        "## Scorecard",
        "",
        "| Task | Variant | Success | Eval pass | Mean first chunk | p50 | p90 | Mean done | n | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for row in rows:
        eval_rate = "-" if row["eval_rate"] is None else f"{row['eval_rate']:.1f}%"
        notes = ", ".join(row["notes"]) if row["notes"] else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    row["task"],
                    row["label"],
                    f"{row['success_rate']:.1f}%",
                    eval_rate,
                    _ms_to_seconds(row["mean_first_response_ms"]),
                    _ms_to_seconds(row["p50_first_response_ms"]),
                    _ms_to_seconds(row["p90_first_response_ms"]),
                    _ms_to_seconds(row["mean_completed_ms"]),
                    str(row["turn_count"]),
                    notes,
                ]
            )
            + " |"
        )

    for task, task_rows in sorted(charts_by_task.items()):
        ranked = sorted(task_rows, key=lambda row: row["mean_first_response_ms"])
        chart = _bar_chart(
            f"{task}: mean time to first spoken chunk",
            [row["label"] for row in ranked],
            [row["mean_first_response_ms"] / 1000 for row in ranked if row["mean_first_response_ms"] is not None],
        )
        lines.extend(["", f"## {task}", ""])
        if chart:
            lines.append(chart)

    lines.extend(
        [
            "",
            "## Guidance",
            "",
            "- Compare success rate and eval pass rate before comparing latency. A faster model that misses the task is not actually better.",
            "- Keep cold-start and warm-follow-up benchmarks in separate suites; mixing them hides resume-session wins.",
            "- Use exact-match or string-match tasks for objective checks, and short summary tasks for voice UX checks.",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a Markdown report from RepoLine latency benchmark JSON."
    )
    parser.add_argument("results_json", help="Path to a JSON file produced by scripts/latency_harness.py")
    parser.add_argument(
        "--markdown-out",
        help="Optional path to write the generated Markdown report.",
    )
    args = parser.parse_args()

    source_path = Path(args.results_json).expanduser().resolve()
    results = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(results, list):
        raise SystemExit("Benchmark results JSON must be an array.")

    report = _render_report(results, source_path=source_path)
    print(report, end="")

    if args.markdown_out:
        output_path = Path(args.markdown_out).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
