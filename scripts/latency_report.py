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


def _benchmark_identity(rows: list[dict[str, Any]]) -> tuple[str, str]:
    families = {str(row.get("benchmark_family") or "").strip() for row in rows}
    revisions = {str(row.get("benchmark_revision") or "").strip() for row in rows}
    if len(families) != 1 or "" in families:
        raise ValueError(
            "Latency report requires exactly one non-empty benchmark_family in the JSONL input."
        )
    if len(revisions) != 1 or "" in revisions:
        raise ValueError(
            "Latency report requires exactly one non-empty benchmark_revision in the JSONL input."
        )
    return next(iter(families)), next(iter(revisions))


def _plan_identity(rows: list[dict[str, Any]]) -> str | None:
    hashes = {str(row.get("plan_sha256") or "").strip() for row in rows}
    if hashes == {""}:
        return None
    if len(hashes) != 1 or "" in hashes:
        raise ValueError(
            "Latency report requires exactly one plan_sha256 when plan fingerprints are present."
        )
    return next(iter(hashes))


def _run_metadata(rows: list[dict[str, Any]]) -> dict[str, str]:
    first_row = rows[0]
    metadata: dict[str, str] = {}
    for key in (
        "run_id",
        "plan_sha256",
        "git_sha_short",
        "host_os",
        "host_arch",
        "python_version",
        "run_started_at_utc",
    ):
        value = first_row.get(key)
        if isinstance(value, str) and value.strip():
            metadata[key] = value.strip()
    return metadata


def _provider_label(row: dict[str, Any]) -> str:
    provider = str(row.get("provider") or "-")
    transport = str(row.get("provider_transport") or "").strip()
    submit_mode = str(row.get("provider_submit_mode") or "").strip()

    if provider == "codex" and not transport:
        base = "Codex CLI"
    elif provider == "cursor" and transport == "app":
        base = "Cursor App"
    elif provider == "cursor" and transport == "cli":
        base = "Cursor Agent CLI"
    elif provider == "gemini" and transport == "cli":
        base = "Gemini CLI"
    elif provider == "claude" and not transport:
        base = "Claude Code"
    elif transport:
        base = f"{provider.title()} {transport.upper()}"
    else:
        base = provider.title()

    if submit_mode:
        return f"{base} ({submit_mode})"
    return base


def _group_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str, str, str]:
    provider_label = _provider_label(row)
    model = row.get("model") or "default"
    provider_transport = row.get("provider_transport") or "-"
    provider_submit_mode = row.get("provider_submit_mode") or "-"
    fresh_session_strategy = row.get("fresh_session_strategy") or "-"
    prompt_variant = row.get("prompt_variant") or row.get("scenario_name") or "-"
    latency_archetype = row.get("latency_archetype") or "-"
    prompt_id = row.get("prompt_id") or "-"
    session_state = row.get("session_state") or "-"
    return (
        str(provider_label),
        str(model),
        str(provider_transport),
        str(provider_submit_mode),
        str(fresh_session_strategy),
        str(prompt_variant),
        str(latency_archetype),
        str(prompt_id),
        str(session_state),
    )


def _failure_reasons(rows: list[dict[str, Any]]) -> dict[str, list[tuple[str, str, int]]]:
    grouped: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        outcome = str(row.get("outcome") or "").strip()
        if not outcome or outcome == "ok":
            continue
        provider_label = _provider_label(row)
        error_message = str(row.get("error_message") or "").strip()
        reason = error_message or "No provider error message recorded."
        grouped[provider_label][(outcome, reason)] += 1

    result: dict[str, list[tuple[str, str, int]]] = {}
    for provider_label, reasons in grouped.items():
        ordered = sorted(
            ((outcome, reason, count) for (outcome, reason), count in reasons.items()),
            key=lambda item: (-item[2], item[0], item[1]),
        )
        result[provider_label] = ordered
    return dict(sorted(result.items()))


def _render_report(rows: list[dict[str, Any]], *, source_path: Path) -> str:
    benchmark_family, benchmark_revision = _benchmark_identity(rows)
    _plan_identity(rows)
    metadata = _run_metadata(rows)
    failure_reasons = _failure_reasons(rows)
    grouped: dict[
        tuple[str, str, str, str, str, str, str, str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)

    lines = [
        "# RepoLine Latency Summary",
        "",
        f"Source: `{source_path}`",
        f"Generated: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`",
        f"Benchmark family: `{benchmark_family}`",
        f"Benchmark revision: `{benchmark_revision}`",
    ]
    if "run_id" in metadata and "run_started_at_utc" in metadata:
        lines.append(f"Run: `{metadata['run_id']}` at `{metadata['run_started_at_utc']}`")
    if (
        "host_os" in metadata
        and "host_arch" in metadata
        and "python_version" in metadata
    ):
        lines.append(
            f"Host: `{metadata['host_os']}` `{metadata['host_arch']}` on Python `{metadata['python_version']}`"
        )
    if "git_sha_short" in metadata:
        lines.append(f"Git: `{metadata['git_sha_short']}`")
    if "plan_sha256" in metadata:
        lines.append(f"Plan SHA-256: `{metadata['plan_sha256'][:12]}`")
    lines.extend(
        [
            "",
            "This is a local diagnostic summary over normalized JSONL turn records.",
            "",
            "| Provider path | Model | Transport | Submit mode | Fresh strategy | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )

    def sort_key(
        item: tuple[
            tuple[str, str, str, str, str, str, str, str, str], list[dict[str, Any]]
        ]
    ) -> tuple[Any, ...]:
        key, group_rows = item
        spoken_values = [
            float(row["spoken_response_latency_ms"])
            for row in group_rows
            if row.get("spoken_response_latency_ms") is not None
        ]
        median_spoken = _percentile(spoken_values, 0.5)
        return (
            key[6],
            key[5],
            median_spoken or float("inf"),
            key[0],
            key[7],
            key[8],
        )

    for key, group_rows in sorted(grouped.items(), key=sort_key):
        (
            provider_label,
            model,
            provider_transport,
            provider_submit_mode,
            fresh_session_strategy,
            prompt_variant,
            latency_archetype,
            prompt_id,
            session_state,
        ) = key
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
        if len(group_rows) < 3:
            warnings.append("thin sample")

        lines.append(
            "| "
            + " | ".join(
                [
                    provider_label,
                    model,
                    provider_transport,
                    provider_submit_mode,
                    fresh_session_strategy,
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
    if failure_reasons:
        lines.extend(
            [
                "",
                "## Failure Reasons",
                "",
            ]
        )
        for provider_label, reasons in failure_reasons.items():
            lines.extend([f"### {provider_label}", ""])
            for outcome, reason, count in reasons:
                lines.append(f"- `{outcome}` x{count}: {reason}")
            lines.append("")

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
