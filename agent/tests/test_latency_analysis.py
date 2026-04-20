from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LATENCY_ANALYSIS_PATH = REPO_ROOT / "scripts" / "latency_analysis.py"


def _load_latency_analysis_module():
    spec = importlib.util.spec_from_file_location(
        "latency_analysis", LATENCY_ANALYSIS_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load scripts/latency_analysis.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_latency_analysis_rejects_mixed_benchmark_identity() -> None:
    module = _load_latency_analysis_module()

    with pytest.raises(ValueError):
        module._benchmark_identity(
            [
                {
                    "benchmark_family": "cross_provider_latency",
                    "benchmark_revision": "v1",
                },
                {
                    "benchmark_family": "cursor_transport",
                    "benchmark_revision": "v1",
                },
            ]
        )


def test_latency_analysis_rejects_mixed_plan_hashes() -> None:
    module = _load_latency_analysis_module()

    with pytest.raises(ValueError):
        module._plan_identity(
            [
                {"plan_sha256": "aaa"},
                {"plan_sha256": "bbb"},
            ]
        )


def test_latency_analysis_main_renders_expected_outputs(tmp_path) -> None:
    module = _load_latency_analysis_module()
    rows = [
        {
            "run_id": "run-123",
            "plan_path": "/tmp/cross-provider-latency-v1.json",
            "plan_sha256": "planhash1234567890",
            "git_sha_short": "abc123d",
            "host_os": "Darwin",
            "host_arch": "arm64",
            "python_version": "3.13.11",
            "run_started_at_utc": "2026-04-20T05:42:00Z",
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "provider": "codex",
            "provider_transport": None,
            "session_state": "fresh",
            "latency_archetype": "trivial-conversation",
            "outcome": "ok",
            "spoken_response_latency_ms": 2400,
            "provider_first_assistant_delta_ms": 1600,
            "completed_turn_ms": 3900,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "cursor",
            "provider_transport": "app",
            "session_state": "fresh",
            "latency_archetype": "trivial-conversation",
            "outcome": "ok",
            "spoken_response_latency_ms": 1100,
            "provider_first_assistant_delta_ms": 800,
            "completed_turn_ms": 2100,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "codex",
            "provider_transport": None,
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 3200,
            "provider_first_assistant_delta_ms": 2100,
            "completed_turn_ms": 4700,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "cursor",
            "provider_transport": "app",
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 1500,
            "provider_first_assistant_delta_ms": 1000,
            "completed_turn_ms": 2600,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "codex",
            "provider_transport": None,
            "session_state": "warm",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 2600,
            "provider_first_assistant_delta_ms": 1800,
            "completed_turn_ms": 4100,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "cursor",
            "provider_transport": "app",
            "session_state": "warm",
            "latency_archetype": "planning-question",
            "outcome": "timed_out",
            "spoken_response_latency_ms": None,
            "provider_first_assistant_delta_ms": None,
            "completed_turn_ms": 90000,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "gemini",
            "provider_transport": "cli",
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "provider_error",
            "error_message": "[API Error: You have exhausted your capacity on this model.]",
            "spoken_response_latency_ms": None,
            "provider_first_assistant_delta_ms": None,
            "completed_turn_ms": 1200,
        },
    ]

    jsonl_path = tmp_path / "cross-provider-latency-v1.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "analysis"

    original_argv = sys.argv
    sys.argv = [
        "latency_analysis.py",
        str(jsonl_path),
        "--output-dir",
        str(output_dir),
    ]
    try:
        assert module.main() == 0
    finally:
        sys.argv = original_argv

    provider_chart = output_dir / "cross-provider-latency-v1-provider-comparison.png"
    archetype_chart = output_dir / "cross-provider-latency-v1-fresh-archetypes.png"
    session_delta_chart = output_dir / "cross-provider-latency-v1-session-deltas.png"
    provider_csv = output_dir / "cross-provider-latency-v1-provider-summary.csv"
    archetype_csv = output_dir / "cross-provider-latency-v1-fresh-archetypes.csv"
    failure_csv = output_dir / "cross-provider-latency-v1-failure-reasons.csv"
    session_delta_csv = output_dir / "cross-provider-latency-v1-session-deltas.csv"
    summary_path = output_dir / "cross-provider-latency-v1-analysis.md"

    assert provider_chart.exists()
    assert archetype_chart.exists()
    assert session_delta_chart.exists()
    assert provider_csv.exists()
    assert archetype_csv.exists()
    assert failure_csv.exists()
    assert session_delta_csv.exists()
    assert summary_path.exists()

    summary = summary_path.read_text(encoding="utf-8")
    assert "Benchmark family: `cross_provider_latency`" in summary
    assert "Benchmark revision: `v1`" in summary
    assert "Run id: `run-123`" in summary
    assert "Git: `abc123d`" in summary
    assert "Plan SHA-256: `planhash1234`" in summary
    assert "Cursor App" in summary
    assert "Fresh Archetype Breakout" in summary
    assert "Session Reuse Deltas" in summary
    assert "Thin Sample Caveats" in summary
    assert "Failure Reasons" in summary
    assert "IQR spoken" in summary
    assert "exhausted your capacity" in summary
    assert "Provider summary CSV" in summary
    assert "Session delta CSV" in summary

    provider_csv_text = provider_csv.read_text(encoding="utf-8")
    assert "session_state,provider_key,provider_label" in provider_csv_text
    assert "cursor:app,Cursor App" in provider_csv_text

    failure_csv_text = failure_csv.read_text(encoding="utf-8")
    assert "provider_label,outcome,count,reason" in failure_csv_text
    assert "Gemini CLI,provider_error,1" in failure_csv_text

    session_delta_csv_text = session_delta_csv.read_text(encoding="utf-8")
    assert (
        "latency_archetype,scope_label,provider_key,provider_label"
        in session_delta_csv_text
    )
    assert ",All Turns,codex,Codex CLI," in session_delta_csv_text


def test_latency_analysis_distinguishes_submit_modes() -> None:
    module = _load_latency_analysis_module()
    rows = [
        {
            "benchmark_family": "cursor_transport",
            "benchmark_revision": "v1",
            "provider": "cursor",
            "provider_transport": "app",
            "provider_submit_mode": "auto",
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 2100,
            "provider_first_assistant_delta_ms": 1100,
            "completed_turn_ms": 2800,
        },
        {
            "benchmark_family": "cursor_transport",
            "benchmark_revision": "v1",
            "provider": "cursor",
            "provider_transport": "app",
            "provider_submit_mode": "active-input",
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 2500,
            "provider_first_assistant_delta_ms": 1400,
            "completed_turn_ms": 3200,
        },
    ]

    summaries = module._summaries_by_provider_and_session(rows)
    labels = [summary.provider_label for summary in summaries["fresh"]]

    assert labels == ["Cursor App (auto)", "Cursor App (active-input)"]


def test_latency_analysis_builds_session_deltas() -> None:
    module = _load_latency_analysis_module()
    rows = [
        {
            "provider": "cursor",
            "provider_transport": "app",
            "provider_submit_mode": "auto",
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 2000,
            "provider_first_assistant_delta_ms": 1400,
            "completed_turn_ms": 2600,
        },
        {
            "provider": "cursor",
            "provider_transport": "app",
            "provider_submit_mode": "auto",
            "session_state": "warm",
            "latency_archetype": "planning-question",
            "outcome": "ok",
            "spoken_response_latency_ms": 1500,
            "provider_first_assistant_delta_ms": 1000,
            "completed_turn_ms": 1900,
        },
    ]

    deltas = module._session_delta_summaries(rows)

    assert len(deltas) == 2
    overall = next(delta for delta in deltas if delta.latency_archetype is None)
    archetype = next(
        delta for delta in deltas if delta.latency_archetype == "planning-question"
    )

    assert overall.provider_label == "Cursor App (auto)"
    assert overall.delta_spoken_ms == -500
    assert overall.delta_spoken_pct == -25
    assert archetype.delta_assistant_ms == -400
    assert archetype.delta_done_ms == -700


def test_latency_analysis_main_renders_single_archetype_failure_only_run(tmp_path) -> None:
    module = _load_latency_analysis_module()
    rows = [
        {
            "run_id": "run-gemini-error",
            "plan_path": "/tmp/repoline-gemini-error-repro.json",
            "plan_sha256": "planhash-single-archetype",
            "git_sha_short": "abc123d",
            "benchmark_family": "provider_failure_repro",
            "benchmark_revision": "v1",
            "provider": "gemini",
            "provider_transport": "cli",
            "session_state": "fresh",
            "latency_archetype": "planning-question",
            "outcome": "provider_error",
            "error_message": "[API Error: You have exhausted your capacity on this model.]",
            "spoken_response_latency_ms": None,
            "provider_first_assistant_delta_ms": None,
            "completed_turn_ms": 9772.7,
        }
    ]

    jsonl_path = tmp_path / "gemini-error-repro.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "analysis"

    original_argv = sys.argv
    sys.argv = [
        "latency_analysis.py",
        str(jsonl_path),
        "--output-dir",
        str(output_dir),
    ]
    try:
        assert module.main() == 0
    finally:
        sys.argv = original_argv

    summary = (output_dir / "gemini-error-repro-analysis.md").read_text(encoding="utf-8")
    assert "Failure Reasons" in summary
    assert "exhausted your capacity" in summary
    assert "IQR spoken" in summary
    assert (output_dir / "gemini-error-repro-session-deltas.png").exists()
    assert (output_dir / "gemini-error-repro-session-deltas.csv").exists()
