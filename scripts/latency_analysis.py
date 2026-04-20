#!/usr/bin/env python3
"""Render latency analysis artifacts from normalized RepoLine JSONL turn records."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


PROVIDER_COLORS = {
    "codex": "#2563eb",
    "cursor:app": "#10b981",
    "cursor:cli": "#f59e0b",
    "gemini:cli": "#ef4444",
    "claude": "#8b5cf6",
}

ARCHETYPE_LABELS = {
    "trivial-conversation": "Trivial Conversation",
    "planning-question": "Planning Question",
    "repo-lookup": "Repo Lookup",
    "light-investigation": "Light Investigation",
}


@dataclass(frozen=True, slots=True)
class ProviderSummary:
    provider_key: str
    provider_label: str
    session_state: str
    latency_archetype: str | None
    color: str
    ok_count: int
    total_count: int
    success_rate: float
    median_spoken_ms: float | None
    p90_spoken_ms: float | None
    q1_spoken_ms: float | None
    q3_spoken_ms: float | None
    ci_low_ms: float | None
    ci_high_ms: float | None
    median_assistant_ms: float | None
    median_done_ms: float | None


@dataclass(frozen=True, slots=True)
class SessionDeltaSummary:
    provider_key: str
    provider_label: str
    latency_archetype: str | None
    color: str
    fresh_ok_count: int
    fresh_total_count: int
    fresh_success_rate: float
    fresh_median_spoken_ms: float | None
    warm_ok_count: int
    warm_total_count: int
    warm_success_rate: float
    warm_median_spoken_ms: float | None
    delta_spoken_ms: float | None
    delta_spoken_pct: float | None
    delta_assistant_ms: float | None
    delta_done_ms: float | None


def _load_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
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
    if families != {next(iter(families))} or "" in families:
        raise ValueError(
            "Latency analysis requires exactly one non-empty benchmark_family across all rows."
        )
    if revisions != {next(iter(revisions))} or "" in revisions:
        raise ValueError(
            "Latency analysis requires exactly one non-empty benchmark_revision across all rows."
        )
    return next(iter(families)), next(iter(revisions))


def _plan_identity(rows: list[dict[str, Any]]) -> str | None:
    hashes = {str(row.get("plan_sha256") or "").strip() for row in rows}
    if hashes == {""}:
        return None
    if len(hashes) != 1 or "" in hashes:
        raise ValueError(
            "Latency analysis requires exactly one plan_sha256 when plan fingerprints are present."
        )
    return next(iter(hashes))


def _run_metadata(rows: list[dict[str, Any]]) -> dict[str, str]:
    first_row = rows[0]
    metadata: dict[str, str] = {}
    for key in (
        "run_id",
        "plan_path",
        "plan_sha256",
        "git_sha",
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


def _provider_key(row: dict[str, Any]) -> str:
    provider = str(row.get("provider") or "-")
    transport = str(row.get("provider_transport") or "").strip()
    submit_mode = str(row.get("provider_submit_mode") or "").strip()
    fresh_session_strategy = str(row.get("fresh_session_strategy") or "").strip()
    parts = [provider]
    if transport:
        parts.append(transport)
    if submit_mode:
        parts.append(f"submit={submit_mode}")
    if fresh_session_strategy:
        parts.append(f"fresh={fresh_session_strategy}")
    return ":".join(parts)


def _provider_label(provider_key: str) -> str:
    parts = provider_key.split(":")
    provider = parts[0]
    transport = ""
    qualifiers: list[str] = []
    for part in parts[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            if key == "submit":
                qualifiers.append(value)
            elif key == "fresh":
                qualifiers.append(value.replace("_", " "))
            else:
                qualifiers.append(f"{key}={value}")
            continue
        if not transport:
            transport = part
        else:
            qualifiers.append(part)

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

    if qualifiers:
        return f"{base} ({', '.join(qualifiers)})"
    return base


def _provider_color(provider_key: str) -> str:
    base_parts = provider_key.split(":")
    base_key = base_parts[0]
    if len(base_parts) > 1 and "=" not in base_parts[1]:
        base_key = f"{base_key}:{base_parts[1]}"
    return PROVIDER_COLORS.get(base_key, "#475569")


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    fraction = position - lower
    return lower_value + (upper_value - lower_value) * fraction


def _bootstrap_median_ci(
    values: list[float],
    *,
    seed: int,
    resamples: int = 2000,
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]

    rng = random.Random(seed)
    medians: list[float] = []
    for _ in range(resamples):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        medians.append(statistics.median(sample))
    return _percentile(medians, 0.025), _percentile(medians, 0.975)


def _stable_seed(*parts: str | None) -> int:
    seed = 17
    for part in parts:
        for character in str(part or ""):
            seed = (seed * 31 + ord(character)) % (2**32)
    return seed


def _metric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        values.append(float(value))
    return values


def _build_summary(
    rows: list[dict[str, Any]],
    *,
    provider_key: str,
    session_state: str,
    latency_archetype: str | None,
) -> ProviderSummary:
    ok_rows = [row for row in rows if row.get("outcome") == "ok"]
    spoken_values = _metric_values(ok_rows, "spoken_response_latency_ms")
    ci_low_ms, ci_high_ms = _bootstrap_median_ci(
        spoken_values,
        seed=_stable_seed(provider_key, session_state, latency_archetype),
    )
    return ProviderSummary(
        provider_key=provider_key,
        provider_label=_provider_label(provider_key),
        session_state=session_state,
        latency_archetype=latency_archetype,
        color=_provider_color(provider_key),
        ok_count=len(ok_rows),
        total_count=len(rows),
        success_rate=(len(ok_rows) / len(rows)) if rows else 0.0,
        median_spoken_ms=_percentile(spoken_values, 0.5),
        p90_spoken_ms=_percentile(spoken_values, 0.9),
        q1_spoken_ms=_percentile(spoken_values, 0.25),
        q3_spoken_ms=_percentile(spoken_values, 0.75),
        ci_low_ms=ci_low_ms,
        ci_high_ms=ci_high_ms,
        median_assistant_ms=_percentile(
            _metric_values(ok_rows, "provider_first_assistant_delta_ms"), 0.5
        ),
        median_done_ms=_percentile(_metric_values(rows, "completed_turn_ms"), 0.5),
    )


def _summaries_by_provider_and_session(
    rows: list[dict[str, Any]],
) -> dict[str, list[ProviderSummary]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(_provider_key(row), str(row.get("session_state") or "-"))].append(row)

    summaries: dict[str, list[ProviderSummary]] = defaultdict(list)
    for (provider_key, session_state), group_rows in grouped.items():
        summaries[session_state].append(
            _build_summary(
                group_rows,
                provider_key=provider_key,
                session_state=session_state,
                latency_archetype=None,
            )
        )

    for session_state, items in summaries.items():
        items.sort(
            key=lambda item: (
                item.median_spoken_ms if item.median_spoken_ms is not None else float("inf"),
                item.provider_label,
            )
        )
    return summaries


def _fresh_archetype_summaries(
    rows: list[dict[str, Any]],
) -> dict[str, list[ProviderSummary]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("session_state") != "fresh":
            continue
        archetype = str(row.get("latency_archetype") or "-")
        grouped[(archetype, _provider_key(row))].append(row)

    summaries: dict[str, list[ProviderSummary]] = defaultdict(list)
    for (archetype, provider_key), group_rows in grouped.items():
        summaries[archetype].append(
            _build_summary(
                group_rows,
                provider_key=provider_key,
                session_state="fresh",
                latency_archetype=archetype,
            )
        )

    for archetype, items in summaries.items():
        items.sort(
            key=lambda item: (
                item.median_spoken_ms if item.median_spoken_ms is not None else float("inf"),
                item.provider_label,
            )
        )
    return summaries


def _compute_delta(warm_value: float | None, fresh_value: float | None) -> float | None:
    if warm_value is None or fresh_value is None:
        return None
    return warm_value - fresh_value


def _compute_delta_pct(warm_value: float | None, fresh_value: float | None) -> float | None:
    if warm_value is None or fresh_value in {None, 0}:
        return None
    return ((warm_value - fresh_value) / fresh_value) * 100


def _session_delta_summaries(rows: list[dict[str, Any]]) -> list[SessionDeltaSummary]:
    provider_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    provider_archetype_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        provider_key = _provider_key(row)
        provider_groups[provider_key].append(row)
        archetype = str(row.get("latency_archetype") or "").strip()
        if archetype:
            provider_archetype_groups[(provider_key, archetype)].append(row)

    grouped_rows: list[tuple[str, str | None, list[dict[str, Any]]]] = [
        (provider_key, None, group_rows)
        for provider_key, group_rows in provider_groups.items()
    ]
    grouped_rows.extend(
        (provider_key, archetype, group_rows)
        for (provider_key, archetype), group_rows in provider_archetype_groups.items()
    )

    results: list[SessionDeltaSummary] = []
    for provider_key, latency_archetype, group_rows in grouped_rows:
        session_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in group_rows:
            session_rows[str(row.get("session_state") or "-")].append(row)
        fresh_rows = session_rows.get("fresh")
        warm_rows = session_rows.get("warm")
        if not fresh_rows or not warm_rows:
            continue

        fresh_summary = _build_summary(
            fresh_rows,
            provider_key=provider_key,
            session_state="fresh",
            latency_archetype=latency_archetype,
        )
        warm_summary = _build_summary(
            warm_rows,
            provider_key=provider_key,
            session_state="warm",
            latency_archetype=latency_archetype,
        )
        results.append(
            SessionDeltaSummary(
                provider_key=provider_key,
                provider_label=_provider_label(provider_key),
                latency_archetype=latency_archetype,
                color=_provider_color(provider_key),
                fresh_ok_count=fresh_summary.ok_count,
                fresh_total_count=fresh_summary.total_count,
                fresh_success_rate=fresh_summary.success_rate,
                fresh_median_spoken_ms=fresh_summary.median_spoken_ms,
                warm_ok_count=warm_summary.ok_count,
                warm_total_count=warm_summary.total_count,
                warm_success_rate=warm_summary.success_rate,
                warm_median_spoken_ms=warm_summary.median_spoken_ms,
                delta_spoken_ms=_compute_delta(
                    warm_summary.median_spoken_ms, fresh_summary.median_spoken_ms
                ),
                delta_spoken_pct=_compute_delta_pct(
                    warm_summary.median_spoken_ms, fresh_summary.median_spoken_ms
                ),
                delta_assistant_ms=_compute_delta(
                    warm_summary.median_assistant_ms, fresh_summary.median_assistant_ms
                ),
                delta_done_ms=_compute_delta(
                    warm_summary.median_done_ms, fresh_summary.median_done_ms
                ),
            )
        )

    results.sort(
        key=lambda item: (
            item.latency_archetype is not None,
            ARCHETYPE_LABELS.get(item.latency_archetype or "", item.latency_archetype or ""),
            item.delta_spoken_ms if item.delta_spoken_ms is not None else float("inf"),
            item.provider_label,
        )
    )
    return results


def _format_seconds(value_ms: float | None) -> str:
    if value_ms is None:
        return "-"
    return f"{value_ms / 1000:.2f}s"


def _format_percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def _format_signed_seconds(value_ms: float | None) -> str:
    if value_ms is None:
        return "-"
    return f"{value_ms / 1000:+.2f}s"


def _format_signed_percent(value_pct: float | None) -> str:
    if value_pct is None:
        return "-"
    return f"{value_pct:+.0f}%"


def _failure_reasons(rows: list[dict[str, Any]]) -> dict[str, list[tuple[str, str, int]]]:
    grouped: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        outcome = str(row.get("outcome") or "").strip()
        if not outcome or outcome == "ok":
            continue
        provider_label = _provider_label(_provider_key(row))
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


def _write_provider_summary_csv(
    summaries_by_session: dict[str, list[ProviderSummary]], *, output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "session_state",
                "provider_key",
                "provider_label",
                "ok_count",
                "total_count",
                "success_rate",
                "median_spoken_ms",
                "p90_spoken_ms",
                "q1_spoken_ms",
                "q3_spoken_ms",
                "ci_low_ms",
                "ci_high_ms",
                "median_assistant_ms",
                "median_done_ms",
            ]
        )
        for session_state in ("fresh", "warm"):
            for summary in summaries_by_session.get(session_state, []):
                writer.writerow(
                    [
                        summary.session_state,
                        summary.provider_key,
                        summary.provider_label,
                        summary.ok_count,
                        summary.total_count,
                        round(summary.success_rate, 6),
                        summary.median_spoken_ms,
                        summary.p90_spoken_ms,
                        summary.q1_spoken_ms,
                        summary.q3_spoken_ms,
                        summary.ci_low_ms,
                        summary.ci_high_ms,
                        summary.median_assistant_ms,
                        summary.median_done_ms,
                    ]
                )


def _write_fresh_archetype_summary_csv(
    summaries_by_archetype: dict[str, list[ProviderSummary]], *, output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "latency_archetype",
                "provider_key",
                "provider_label",
                "session_state",
                "ok_count",
                "total_count",
                "success_rate",
                "median_spoken_ms",
                "p90_spoken_ms",
                "q1_spoken_ms",
                "q3_spoken_ms",
                "ci_low_ms",
                "ci_high_ms",
                "median_assistant_ms",
                "median_done_ms",
            ]
        )
        for archetype in ARCHETYPE_LABELS:
            for summary in summaries_by_archetype.get(archetype, []):
                writer.writerow(
                    [
                        summary.latency_archetype,
                        summary.provider_key,
                        summary.provider_label,
                        summary.session_state,
                        summary.ok_count,
                        summary.total_count,
                        round(summary.success_rate, 6),
                        summary.median_spoken_ms,
                        summary.p90_spoken_ms,
                        summary.q1_spoken_ms,
                        summary.q3_spoken_ms,
                        summary.ci_low_ms,
                        summary.ci_high_ms,
                        summary.median_assistant_ms,
                        summary.median_done_ms,
                    ]
                )


def _write_failure_reasons_csv(
    failure_reasons: dict[str, list[tuple[str, str, int]]], *, output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["provider_label", "outcome", "count", "reason"])
        for provider_label, reasons in failure_reasons.items():
            for outcome, reason, count in reasons:
                writer.writerow([provider_label, outcome, count, reason])


def _write_session_delta_summary_csv(
    session_deltas: list[SessionDeltaSummary], *, output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "latency_archetype",
                "scope_label",
                "provider_key",
                "provider_label",
                "fresh_ok_count",
                "fresh_total_count",
                "fresh_success_rate",
                "fresh_median_spoken_ms",
                "warm_ok_count",
                "warm_total_count",
                "warm_success_rate",
                "warm_median_spoken_ms",
                "delta_spoken_ms",
                "delta_spoken_pct",
                "delta_assistant_ms",
                "delta_done_ms",
            ]
        )
        for item in session_deltas:
            scope_label = (
                ARCHETYPE_LABELS.get(item.latency_archetype, item.latency_archetype or "")
                if item.latency_archetype
                else "All Turns"
            )
            writer.writerow(
                [
                    item.latency_archetype,
                    scope_label,
                    item.provider_key,
                    item.provider_label,
                    item.fresh_ok_count,
                    item.fresh_total_count,
                    round(item.fresh_success_rate, 6),
                    item.fresh_median_spoken_ms,
                    item.warm_ok_count,
                    item.warm_total_count,
                    round(item.warm_success_rate, 6),
                    item.warm_median_spoken_ms,
                    item.delta_spoken_ms,
                    item.delta_spoken_pct,
                    item.delta_assistant_ms,
                    item.delta_done_ms,
                ]
            )


def _render_provider_comparison_chart(
    summaries_by_session: dict[str, list[ProviderSummary]],
    *,
    title: str,
    output_path: Path,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    sessions = ["fresh", "warm"]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6), sharex=True)

    for index, session in enumerate(sessions):
        ax = axes[index]
        summaries = summaries_by_session.get(session, [])
        if not summaries:
            ax.set_title(f"{session.title()} turns")
            ax.text(
                0.5,
                0.5,
                "No rows",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color="#64748b",
            )
            ax.axis("off")
            continue

        y_positions = list(range(len(summaries)))
        medians = [
            (summary.median_spoken_ms or 0.0) / 1000 for summary in summaries
        ]
        bar_colors = [
            summary.color if summary.median_spoken_ms is not None else "#cbd5e1"
            for summary in summaries
        ]
        lower_errors = [
            max(0.0, medians[i] - ((summary.ci_low_ms or summary.median_spoken_ms or 0.0) / 1000))
            for i, summary in enumerate(summaries)
        ]
        upper_errors = [
            max(0.0, ((summary.ci_high_ms or summary.median_spoken_ms or 0.0) / 1000) - medians[i])
            for i, summary in enumerate(summaries)
        ]
        ax.barh(
            y_positions,
            medians,
            color=bar_colors,
            xerr=[lower_errors, upper_errors],
            ecolor="#0f172a",
            capsize=4,
        )
        ax.set_yticks(y_positions)
        ax.set_yticklabels([summary.provider_label for summary in summaries])
        ax.invert_yaxis()
        ax.set_xlabel("Median spoken response latency (seconds)")
        ax.set_title(f"{session.title()} turns")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        for y_position, summary, median in zip(y_positions, summaries, medians, strict=True):
            if summary.median_spoken_ms is None:
                ax.text(
                    0.18,
                    y_position,
                    f"no ok rows  ok {summary.ok_count}/{summary.total_count}",
                    va="center",
                    ha="left",
                    fontsize=9,
                    color="#64748b",
                )
                continue
            label_x = max(
                median,
                (summary.ci_high_ms or summary.median_spoken_ms or 0.0) / 1000,
            ) + 0.18
            ax.text(
                label_x,
                y_position,
                f"{median:.2f}s  ok {summary.ok_count}/{summary.total_count}",
                va="center",
                ha="left",
                fontsize=9,
                color="#0f172a",
            )

    fig.suptitle(title, fontsize=16, fontweight="bold")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_archetype_chart(
    summaries_by_archetype: dict[str, list[ProviderSummary]],
    *,
    title: str,
    output_path: Path,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    ordered_archetypes = [
        archetype for archetype in ARCHETYPE_LABELS if archetype in summaries_by_archetype
    ]
    if not ordered_archetypes:
        raise ValueError("No fresh archetype rows were available for analysis.")

    figure_rows = math.ceil(len(ordered_archetypes) / 2)
    fig, axes = plt.subplots(figure_rows, 2, figsize=(14, 4.6 * figure_rows))
    if figure_rows == 1:
        axes_list = list(axes)
    else:
        axes_list = [axis for row in axes for axis in row]

    for axis in axes_list[len(ordered_archetypes) :]:
        axis.axis("off")

    for axis, archetype in zip(axes_list, ordered_archetypes):
        summaries = summaries_by_archetype[archetype]
        y_positions = list(range(len(summaries)))
        medians = [
            (summary.median_spoken_ms or 0.0) / 1000 for summary in summaries
        ]
        bar_colors = [
            summary.color if summary.median_spoken_ms is not None else "#cbd5e1"
            for summary in summaries
        ]
        lower_errors = [
            max(0.0, medians[i] - ((summary.ci_low_ms or summary.median_spoken_ms or 0.0) / 1000))
            for i, summary in enumerate(summaries)
        ]
        upper_errors = [
            max(0.0, ((summary.ci_high_ms or summary.median_spoken_ms or 0.0) / 1000) - medians[i])
            for i, summary in enumerate(summaries)
        ]
        axis.barh(
            y_positions,
            medians,
            color=bar_colors,
            xerr=[lower_errors, upper_errors],
            ecolor="#0f172a",
            capsize=4,
        )
        axis.set_yticks(y_positions)
        axis.set_yticklabels([summary.provider_label for summary in summaries])
        axis.invert_yaxis()
        axis.set_title(ARCHETYPE_LABELS.get(archetype, archetype))
        axis.set_xlabel("Fresh median spoken latency (seconds)")
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

        for y_position, summary, median in zip(y_positions, summaries, medians, strict=True):
            if summary.median_spoken_ms is None:
                axis.text(
                    0.18,
                    y_position,
                    f"no ok rows  ok {summary.ok_count}/{summary.total_count}",
                    va="center",
                    ha="left",
                    fontsize=9,
                    color="#64748b",
                )
                continue
            label_x = max(
                median,
                (summary.ci_high_ms or summary.median_spoken_ms or 0.0) / 1000,
            ) + 0.18
            axis.text(
                label_x,
                y_position,
                f"{median:.2f}s  ok {summary.ok_count}/{summary.total_count}",
                va="center",
                ha="left",
                fontsize=9,
                color="#0f172a",
            )

    fig.suptitle(title, fontsize=16, fontweight="bold")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_session_delta_chart(
    session_deltas: list[SessionDeltaSummary], *, title: str, output_path: Path
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    overall_deltas = [
        item
        for item in session_deltas
        if item.latency_archetype is None and item.delta_spoken_ms is not None
    ]

    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    if not overall_deltas:
        ax.text(
            0.5,
            0.5,
            "No comparable fresh/warm provider rows",
            transform=ax.transAxes,
            ha="center",
            va="center",
            color="#64748b",
        )
        ax.axis("off")
    else:
        overall_deltas.sort(key=lambda item: item.delta_spoken_ms or 0.0)
        y_positions = list(range(len(overall_deltas)))
        deltas = [(item.delta_spoken_ms or 0.0) / 1000 for item in overall_deltas]
        colors = [item.color for item in overall_deltas]

        ax.barh(y_positions, deltas, color=colors)
        ax.axvline(0.0, color="#0f172a", linewidth=1.2)
        ax.set_yticks(y_positions)
        ax.set_yticklabels([item.provider_label for item in overall_deltas])
        ax.invert_yaxis()
        ax.set_xlabel("Warm minus fresh median spoken latency (seconds)")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        for y_position, item, delta_seconds in zip(
            y_positions, overall_deltas, deltas, strict=True
        ):
            direction = "faster" if delta_seconds < 0 else "slower" if delta_seconds > 0 else "flat"
            fresh_text = _format_seconds(item.fresh_median_spoken_ms)
            warm_text = _format_seconds(item.warm_median_spoken_ms)
            label = (
                f"{delta_seconds:+.2f}s  {direction}  "
                f"{fresh_text} -> {warm_text}"
            )
            if delta_seconds >= 0:
                x_position = delta_seconds + 0.12
                ha = "left"
            else:
                x_position = delta_seconds - 0.12
                ha = "right"
            ax.text(
                x_position,
                y_position,
                label,
                va="center",
                ha=ha,
                fontsize=9,
                color="#0f172a",
            )

    fig.suptitle(title, fontsize=16, fontweight="bold")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_summary_markdown(
    *,
    rows: list[dict[str, Any]],
    benchmark_family: str,
    benchmark_revision: str,
    source_paths: list[Path],
    summaries_by_session: dict[str, list[ProviderSummary]],
    summaries_by_archetype: dict[str, list[ProviderSummary]],
    session_deltas: list[SessionDeltaSummary],
    provider_chart_path: Path,
    archetype_chart_path: Path,
    session_delta_chart_path: Path,
    provider_csv_path: Path,
    archetype_csv_path: Path,
    failure_reasons_csv_path: Path,
    session_delta_csv_path: Path,
) -> str:
    metadata = _run_metadata(rows)
    failure_reasons = _failure_reasons(rows)
    thin_sample_lines: list[str] = []
    lines = [
        "# RepoLine Latency Analysis",
        "",
        f"- Benchmark family: `{benchmark_family}`",
        f"- Benchmark revision: `{benchmark_revision}`",
        f"- Generated: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`",
        f"- Rows: `{len(rows)}`",
        "",
        "## Sources",
        "",
    ]
    if "run_id" in metadata:
        lines.insert(4, f"- Run id: `{metadata['run_id']}`")
    if "run_started_at_utc" in metadata:
        lines.insert(5, f"- Run started: `{metadata['run_started_at_utc']}`")
    if "git_sha_short" in metadata:
        lines.insert(6, f"- Git: `{metadata['git_sha_short']}`")
    if (
        "host_os" in metadata
        and "host_arch" in metadata
        and "python_version" in metadata
    ):
        lines.insert(
            7,
            f"- Host: `{metadata['host_os']}` `{metadata['host_arch']}` on Python `{metadata['python_version']}`",
        )
    if "plan_path" in metadata:
        lines.insert(8, f"- Plan path: `{metadata['plan_path']}`")
    if "plan_sha256" in metadata:
        lines.insert(9, f"- Plan SHA-256: `{metadata['plan_sha256'][:12]}`")
    for source_path in source_paths:
        lines.append(f"- `{source_path}`")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Provider comparison chart: `{provider_chart_path}`",
            f"- Fresh archetype chart: `{archetype_chart_path}`",
            f"- Session delta chart: `{session_delta_chart_path}`",
            f"- Provider summary CSV: `{provider_csv_path}`",
            f"- Fresh archetype summary CSV: `{archetype_csv_path}`",
            f"- Failure reasons CSV: `{failure_reasons_csv_path}`",
            f"- Session delta CSV: `{session_delta_csv_path}`",
            "",
            "## Provider Success And Latency",
            "",
            "| Session | Provider | ok/n | Success | Median spoken | p90 spoken | IQR spoken | 95% median CI | Median assistant | Median done |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for session in ("fresh", "warm"):
        for summary in summaries_by_session.get(session, []):
            if summary.total_count < 3:
                thin_sample_lines.append(
                    f"- `{session}` `{summary.provider_label}` has only `{summary.total_count}` row(s); treat it as directional."
                )
            success_rate = _format_percent(summary.success_rate) if summary.total_count else "-"
            iqr_text = (
                f"{_format_seconds(summary.q1_spoken_ms)} to {_format_seconds(summary.q3_spoken_ms)}"
                if summary.q1_spoken_ms is not None and summary.q3_spoken_ms is not None
                else "-"
            )
            ci_text = (
                f"{_format_seconds(summary.ci_low_ms)} to {_format_seconds(summary.ci_high_ms)}"
                if summary.ci_low_ms is not None and summary.ci_high_ms is not None
                else "-"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        session,
                        summary.provider_label,
                        f"{summary.ok_count}/{summary.total_count}",
                        success_rate,
                        _format_seconds(summary.median_spoken_ms),
                        _format_seconds(summary.p90_spoken_ms),
                        iqr_text,
                        ci_text,
                        _format_seconds(summary.median_assistant_ms),
                        _format_seconds(summary.median_done_ms),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Fresh Archetype Breakout",
            "",
            "| Archetype | Provider | ok/n | Median spoken | IQR spoken | 95% median CI |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for archetype in ARCHETYPE_LABELS:
        for summary in summaries_by_archetype.get(archetype, []):
            if summary.total_count < 3:
                thin_sample_lines.append(
                    f"- `{ARCHETYPE_LABELS.get(archetype, archetype)}` / `{summary.provider_label}` has only `{summary.total_count}` row(s)."
                )
            ci_text = (
                f"{_format_seconds(summary.ci_low_ms)} to {_format_seconds(summary.ci_high_ms)}"
                if summary.ci_low_ms is not None and summary.ci_high_ms is not None
                else "-"
            )
            iqr_text = (
                f"{_format_seconds(summary.q1_spoken_ms)} to {_format_seconds(summary.q3_spoken_ms)}"
                if summary.q1_spoken_ms is not None and summary.q3_spoken_ms is not None
                else "-"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        ARCHETYPE_LABELS.get(archetype, archetype),
                        summary.provider_label,
                        f"{summary.ok_count}/{summary.total_count}",
                        _format_seconds(summary.median_spoken_ms),
                        iqr_text,
                        ci_text,
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Session Reuse Deltas",
            "",
            "| Scope | Provider | Fresh ok/n | Warm ok/n | Fresh median spoken | Warm median spoken | Delta spoken | Delta % | Delta assistant | Delta done |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in session_deltas:
        scope_label = (
            ARCHETYPE_LABELS.get(item.latency_archetype, item.latency_archetype or "")
            if item.latency_archetype
            else "All Turns"
        )
        if item.fresh_total_count < 3 or item.warm_total_count < 3:
            thin_sample_lines.append(
                f"- `{scope_label}` / `{item.provider_label}` has a thin session-delta sample (`fresh {item.fresh_total_count}`, `warm {item.warm_total_count}`)."
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    scope_label,
                    item.provider_label,
                    f"{item.fresh_ok_count}/{item.fresh_total_count}",
                    f"{item.warm_ok_count}/{item.warm_total_count}",
                    _format_seconds(item.fresh_median_spoken_ms),
                    _format_seconds(item.warm_median_spoken_ms),
                    _format_signed_seconds(item.delta_spoken_ms),
                    _format_signed_percent(item.delta_spoken_pct),
                    _format_signed_seconds(item.delta_assistant_ms),
                    _format_signed_seconds(item.delta_done_ms),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This analysis rejects mixed benchmark families and revisions by default.",
            "- It also rejects mixed plan hashes when plan fingerprints are present.",
            "- Provider labels include transport and submit-mode qualifiers when those are part of the experiment contract.",
            "- The provider comparison chart keeps `fresh` and `warm` separate on purpose.",
            "- The archetype chart uses `fresh` turns only so it stays tied to one comparable prompt pack.",
            "- Session delta rows report `warm - fresh`, so negative values mean a warm path is faster.",
            "- The CSV artifacts are tidy exports for notebooks, slide decks, and downstream statistical work.",
        ]
    )
    if thin_sample_lines:
        lines.extend(
            [
                "",
                "## Thin Sample Caveats",
                "",
                *dict.fromkeys(thin_sample_lines),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results_jsonl",
        nargs="+",
        help="One or more JSONL files produced by scripts/latency_harness.py",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for charts and the markdown summary. Defaults to the first JSONL parent.",
    )
    parser.add_argument(
        "--prefix",
        help="Artifact filename prefix. Defaults to the first JSONL stem.",
    )
    args = parser.parse_args()

    source_paths = [Path(path).expanduser().resolve() for path in args.results_jsonl]
    rows = _load_rows(source_paths)
    if not rows:
        raise ValueError("No JSONL rows were found.")

    benchmark_family, benchmark_revision = _benchmark_identity(rows)
    _plan_identity(rows)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else source_paths[0].parent
    )
    prefix = args.prefix or source_paths[0].stem

    summaries_by_session = _summaries_by_provider_and_session(rows)
    summaries_by_archetype = _fresh_archetype_summaries(rows)
    session_deltas = _session_delta_summaries(rows)
    failure_reasons = _failure_reasons(rows)

    provider_chart_path = output_dir / f"{prefix}-provider-comparison.png"
    archetype_chart_path = output_dir / f"{prefix}-fresh-archetypes.png"
    session_delta_chart_path = output_dir / f"{prefix}-session-deltas.png"
    provider_csv_path = output_dir / f"{prefix}-provider-summary.csv"
    archetype_csv_path = output_dir / f"{prefix}-fresh-archetypes.csv"
    failure_reasons_csv_path = output_dir / f"{prefix}-failure-reasons.csv"
    session_delta_csv_path = output_dir / f"{prefix}-session-deltas.csv"
    summary_path = output_dir / f"{prefix}-analysis.md"

    _render_provider_comparison_chart(
        summaries_by_session,
        title=f"RepoLine {benchmark_family} {benchmark_revision}: provider comparison",
        output_path=provider_chart_path,
    )
    _render_archetype_chart(
        summaries_by_archetype,
        title=f"RepoLine {benchmark_family} {benchmark_revision}: fresh archetype comparison",
        output_path=archetype_chart_path,
    )
    _render_session_delta_chart(
        session_deltas,
        title=f"RepoLine {benchmark_family} {benchmark_revision}: warm vs fresh delta",
        output_path=session_delta_chart_path,
    )
    _write_provider_summary_csv(summaries_by_session, output_path=provider_csv_path)
    _write_fresh_archetype_summary_csv(
        summaries_by_archetype, output_path=archetype_csv_path
    )
    _write_failure_reasons_csv(failure_reasons, output_path=failure_reasons_csv_path)
    _write_session_delta_summary_csv(session_deltas, output_path=session_delta_csv_path)

    summary = _render_summary_markdown(
        rows=rows,
        benchmark_family=benchmark_family,
        benchmark_revision=benchmark_revision,
        source_paths=source_paths,
        summaries_by_session=summaries_by_session,
        summaries_by_archetype=summaries_by_archetype,
        session_deltas=session_deltas,
        provider_chart_path=provider_chart_path,
        archetype_chart_path=archetype_chart_path,
        session_delta_chart_path=session_delta_chart_path,
        provider_csv_path=provider_csv_path,
        archetype_csv_path=archetype_csv_path,
        failure_reasons_csv_path=failure_reasons_csv_path,
        session_delta_csv_path=session_delta_csv_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")

    print(f"analysis summary: {summary_path}")
    print(f"provider chart: {provider_chart_path}")
    print(f"fresh archetype chart: {archetype_chart_path}")
    print(f"session delta chart: {session_delta_chart_path}")
    print(f"provider summary csv: {provider_csv_path}")
    print(f"fresh archetypes csv: {archetype_csv_path}")
    print(f"failure reasons csv: {failure_reasons_csv_path}")
    print(f"session delta csv: {session_delta_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
