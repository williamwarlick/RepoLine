#!/usr/bin/env python3
"""Render a static SVG latency snapshot from checked-in RepoLine JSONL artifacts."""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    label: str
    median_ms: float
    sample_count: int
    color: str


def _load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _median_ms(rows: list[dict[str, object]]) -> float:
    values = [
        float(row["spoken_response_latency_ms"])
        for row in rows
        if row.get("outcome") == "ok" and row.get("spoken_response_latency_ms") is not None
    ]
    if not values:
        raise ValueError("No ok spoken_response_latency_ms values found.")
    return statistics.median(values)


def _group_rows(
    rows: list[dict[str, object]],
    *,
    key_fn,
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        key = key_fn(row)
        if key is None:
            continue
        grouped.setdefault(key, []).append(row)
    return grouped


def _planning_series(path: Path) -> list[SeriesPoint]:
    rows = _load_rows(path)
    label_map = {
        "codex": ("Codex CLI", "#2563eb"),
        "cursor:cli": ("Cursor Agent CLI", "#f59e0b"),
        "gemini:cli": ("Gemini CLI", "#ef4444"),
    }

    grouped = _group_rows(
        rows,
        key_fn=lambda row: (
            f"{row.get('provider')}:{row.get('provider_transport')}"
            if row.get("provider_transport")
            else str(row.get("provider"))
        ),
    )

    series: list[SeriesPoint] = []
    for key, group_rows in grouped.items():
        if key not in label_map:
            continue
        label, color = label_map[key]
        series.append(
            SeriesPoint(
                label=label,
                median_ms=_median_ms(group_rows),
                sample_count=sum(1 for row in group_rows if row.get("outcome") == "ok"),
                color=color,
            )
        )
    return sorted(series, key=lambda point: point.median_ms)


def _cursor_runtime_series(path: Path) -> list[SeriesPoint]:
    rows = _load_rows(path)
    label_map = {
        "app": ("Cursor App", "#10b981"),
        "cli": ("Cursor Agent CLI", "#f59e0b"),
    }
    grouped = _group_rows(
        rows,
        key_fn=lambda row: str(row.get("provider_transport") or ""),
    )
    series: list[SeriesPoint] = []
    for key, group_rows in grouped.items():
        if key not in label_map:
            continue
        label, color = label_map[key]
        series.append(
            SeriesPoint(
                label=label,
                median_ms=_median_ms(group_rows),
                sample_count=sum(1 for row in group_rows if row.get("outcome") == "ok"),
                color=color,
            )
        )
    return sorted(series, key=lambda point: point.median_ms)


def _seconds_label(value_ms: float) -> str:
    return f"{value_ms / 1000:.2f}s"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_svg(
    *,
    planning_series: list[SeriesPoint],
    cursor_series: list[SeriesPoint],
    planning_source: str,
    cursor_source: str,
) -> str:
    width = 1200
    height = 760
    padding_left = 72
    chart_left = 330
    chart_right = 1080
    chart_width = chart_right - chart_left
    bar_height = 34
    row_gap = 26
    tick_values = [0, 5, 10, 15, 20, 25]
    global_max_seconds = max(
        max(point.median_ms for point in planning_series) / 1000,
        max(point.median_ms for point in cursor_series) / 1000,
        max(tick_values),
    )

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">RepoLine latency snapshot</title>',
        '<desc id="desc">Two benchmark panels showing median spoken response latency from checked-in RepoLine JSONL artifacts. Lower is better.</desc>',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<rect x="24" y="24" width="1152" height="712" rx="24" fill="#ffffff" stroke="#e2e8f0"/>',
        '<text x="72" y="78" fill="#0f172a" font-size="30" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif" font-weight="700">RepoLine Latency Snapshot</text>',
        '<text x="72" y="108" fill="#475569" font-size="16" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif">Median spoken response latency from checked-in local benchmark artifacts. Lower is better.</text>',
    ]

    def draw_panel(title: str, subtitle: str, y_start: int, series: list[SeriesPoint]) -> int:
        lines.append(
            f'<text x="{padding_left}" y="{y_start}" fill="#0f172a" font-size="22" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif" font-weight="700">{_escape(title)}</text>'
        )
        lines.append(
            f'<text x="{padding_left}" y="{y_start + 24}" fill="#64748b" font-size="14" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif">{_escape(subtitle)}</text>'
        )
        axis_y = y_start + 52
        for tick in tick_values:
            x = chart_left + (tick / global_max_seconds) * chart_width
            lines.append(
                f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 178}" stroke="#e2e8f0" stroke-width="1"/>'
            )
            lines.append(
                f'<text x="{x:.1f}" y="{axis_y - 10}" fill="#94a3b8" font-size="12" text-anchor="middle" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{tick}s</text>'
            )

        row_y = axis_y + 20
        for point in series:
            bar_width = (point.median_ms / 1000 / global_max_seconds) * chart_width
            lines.append(
                f'<text x="{padding_left}" y="{row_y + 22}" fill="#0f172a" font-size="16" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif">{_escape(point.label)}</text>'
            )
            lines.append(
                f'<text x="{padding_left}" y="{row_y + 42}" fill="#64748b" font-size="12" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif">n={point.sample_count}</text>'
            )
            lines.append(
                f'<rect x="{chart_left}" y="{row_y}" width="{chart_width}" height="{bar_height}" rx="10" fill="#e2e8f0"/>'
            )
            lines.append(
                f'<rect x="{chart_left}" y="{row_y}" width="{bar_width:.1f}" height="{bar_height}" rx="10" fill="{point.color}"/>'
            )
            lines.append(
                f'<text x="{chart_left + bar_width + 12:.1f}" y="{row_y + 22}" fill="#0f172a" font-size="15" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{_escape(_seconds_label(point.median_ms))}</text>'
            )
            row_y += bar_height + row_gap
        return row_y

    panel_one_end = draw_panel(
        "Planning Smoke Pack",
        "Artifact: output/latency/planning-latency-smoke-postprompt.jsonl",
        164,
        planning_series,
    )
    draw_panel(
        "Cursor Runtime Comparison",
        "Artifact: output/latency/cursor-app-promotion-runtime-20260419.jsonl",
        panel_one_end + 52,
        cursor_series,
    )

    lines.extend(
        [
            '<text x="72" y="704" fill="#64748b" font-size="13" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif">',
            f'Sources: {_escape(planning_source)} and {_escape(cursor_source)}',
            "</text>",
            '<text x="72" y="724" fill="#94a3b8" font-size="12" font-family="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif">This snapshot is a README summary, not a full report. See output/latency/*.md for the detailed turn-level breakdowns.</text>',
            "</svg>",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--planning-jsonl",
        default="output/latency/planning-latency-smoke-postprompt.jsonl",
        help="JSONL artifact for the cross-provider planning smoke snapshot.",
    )
    parser.add_argument(
        "--cursor-jsonl",
        default="output/latency/cursor-app-promotion-runtime-20260419.jsonl",
        help="JSONL artifact for the Cursor app vs CLI runtime comparison.",
    )
    parser.add_argument(
        "--svg-out",
        default="docs/assets/repoline-latency-snapshot-2026-04-19.svg",
        help="Path to write the generated SVG.",
    )
    args = parser.parse_args()

    planning_path = Path(args.planning_jsonl).expanduser().resolve()
    cursor_path = Path(args.cursor_jsonl).expanduser().resolve()
    output_path = Path(args.svg_out).expanduser().resolve()

    svg = _render_svg(
        planning_series=_planning_series(planning_path),
        cursor_series=_cursor_runtime_series(cursor_path),
        planning_source=str(planning_path.relative_to(Path.cwd().resolve())),
        cursor_source=str(cursor_path.relative_to(Path.cwd().resolve())),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
