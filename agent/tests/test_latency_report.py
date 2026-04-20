from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LATENCY_REPORT_PATH = REPO_ROOT / "scripts" / "latency_report.py"


def _load_latency_report_module():
    spec = importlib.util.spec_from_file_location(
        "latency_report", LATENCY_REPORT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load scripts/latency_report.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_latency_report_keeps_cursor_paths_distinct(tmp_path) -> None:
    module = _load_latency_report_module()
    rows = [
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "cursor",
            "provider_transport": "app",
            "provider_submit_mode": "auto",
            "fresh_session_strategy": "new_composer",
            "model": "composer-2-fast",
            "prompt_variant": "current_baseline",
            "latency_archetype": "planning-question",
            "prompt_id": "repo-summary-1",
            "session_state": "fresh",
            "outcome": "ok",
            "spoken_response_latency_ms": 2400,
            "provider_first_assistant_delta_ms": 1400,
            "completed_turn_ms": 3100,
        },
        {
            "benchmark_family": "cross_provider_latency",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "cursor",
            "provider_transport": "cli",
            "provider_submit_mode": None,
            "fresh_session_strategy": None,
            "model": "composer-2-fast",
            "prompt_variant": "current_baseline",
            "latency_archetype": "planning-question",
            "prompt_id": "repo-summary-1",
            "session_state": "fresh",
            "outcome": "ok",
            "spoken_response_latency_ms": 5400,
            "provider_first_assistant_delta_ms": 3400,
            "completed_turn_ms": 7100,
        },
    ]

    jsonl_path = tmp_path / "cross-provider-latency-v1.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    report = module._render_report(rows, source_path=jsonl_path)

    assert "Cursor App (auto)" in report
    assert "Cursor Agent CLI" in report
    assert "Plan SHA-256: `planhash1234`" in report
    assert "| Cursor App (auto) | composer-2-fast | app | auto | new_composer |" in report
    assert "| Cursor Agent CLI | composer-2-fast | cli | - | - |" in report
    assert "thin sample" in report


def test_latency_report_includes_failure_reasons(tmp_path) -> None:
    module = _load_latency_report_module()
    rows = [
        {
            "benchmark_family": "provider_failure_repro",
            "benchmark_revision": "v1",
            "plan_sha256": "planhash1234567890",
            "provider": "gemini",
            "provider_transport": "cli",
            "model": "gemini-2.5-flash",
            "prompt_variant": "current_baseline",
            "latency_archetype": "planning-question",
            "prompt_id": "repo-summary-1",
            "session_state": "fresh",
            "outcome": "provider_error",
            "error_message": "[API Error: You have exhausted your capacity on this model.]",
            "spoken_response_latency_ms": None,
            "provider_first_assistant_delta_ms": None,
            "completed_turn_ms": 9772.7,
        },
    ]

    jsonl_path = tmp_path / "gemini-error-repro.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    report = module._render_report(rows, source_path=jsonl_path)

    assert "## Failure Reasons" in report
    assert "exhausted your capacity" in report
