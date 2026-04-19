#!/usr/bin/env python3
"""Render a local Markdown latency summary from RepoLine JSONL turn records."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    provider = row.get("provider") or "-"
    model = row.get("model") or "default"
    prompt_variant = row.get("prompt_variant") or row.get("scenario_name") or "-"
    latency_archetype = row.get("latency_archetype") or "-"
    prompt_id = row.get("prompt_id") or "-"
    session_state = row.get("session_state") or "-"
    return (
        str(provider),
        str(model),
        str(prompt_variant),
        str(latency_archetype),
        str(prompt_id),
        str(session_state),
    )


def _render_report(rows: list[dict[str, Any]], *, source_path: Path) -> str:
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)

    lines = [
        "# RepoLine Latency Summary",
        "",
        f"Source: `{source_path}`",
        f"Generated: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`",
        "",
        "This is a local diagnostic summary over normalized JSONL turn records.",
        "",
        "| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    def sort_key(item: tuple[tuple[str, str, str, str, str, str], list[dict[str, Any]]]) -> tuple[Any, ...]:
        key, group_rows = item
        spoken_values = [
            float(row["spoken_response_latency_ms"])
            for row in group_rows
            if row.get("spoken_response_latency_ms") is not None
        ]
        median_spoken = _percentile(spoken_values, 0.5)
        return (key[3], key[2], median_spoken or float("inf"), key[0], key[4], key[5])

    for key, group_rows in sorted(grouped.items(), key=sort_key):
        provider, model, prompt_variant, latency_archetype, prompt_id, session_state = key
        ok_count = sum(1 for row in group_rows if row.get("outcome") == "ok")
        spoken_values = [
            float(row["spoken_response_latency_ms"])
            for row in group_rows
            if row.get("spoken_response_latency_ms") is not None
        ]
        assistant_values = [
            float(row["provider_first_assistant_delta_ms"])
            for row in group_rows
            if row.get("provider_first_assistant_delta_ms") is not None
        ]
        done_values = [
            float(row["completed_turn_ms"])
            for row in group_rows
            if row.get("completed_turn_ms") is not None
        ]

        warnings: list[str] = []
        median_spoken = _percentile(spoken_values, 0.5)
        p90_spoken = _percentile(spoken_values, 0.9)
        if median_spoken is not None and median_spoken > 10000:
            warnings.append("median spoken > 10s")
        if p90_spoken is not None and p90_spoken > 30000:
            warnings.append("p90 spoken > 30s")
        if any(row.get("outcome") == "timed_out" for row in group_rows):
            warnings.append("timeout observed")
        if any(row.get("outcome") == "provider_error" for row in group_rows):
            warnings.append("provider error observed")
        if any(row.get("outcome") == "no_speech" for row in group_rows):
            warnings.append("no speech observed")

        lines.append(
            "| "
            + " | ".join(
                [
                    provider,
                    model,
                    prompt_variant,
                    latency_archetype,
                    prompt_id,
                    session_state,
                    f"{ok_count}/{len(group_rows)}",
                    _ms_to_seconds(median_spoken),
                    _ms_to_seconds(p90_spoken),
                    _ms_to_seconds(_percentile(assistant_values, 0.5)),
                    _ms_to_seconds(_percentile(assistant_values, 0.9)),
                    _ms_to_seconds(_percentile(done_values, 0.5)),
                    ", ".join(warnings) if warnings else "-",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `Median spoken` is the headline latency for the current scenario-runner harness.",
            "- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.",
            "- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a Markdown report from RepoLine JSONL latency records."
    )
    parser.add_argument("results_jsonl", help="Path to a JSONL file produced by scripts/latency_harness.py")
    parser.add_argument(
        "--markdown-out",
        help="Optional path to write the generated Markdown report.",
    )
    args = parser.parse_args()

    source_path = Path(args.results_jsonl).expanduser().resolve()
    rows = _load_rows(source_path)
    report = _render_report(rows, source_path=source_path)
    print(report, end="")

    if args.markdown_out:
        output_path = Path(args.markdown_out).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
