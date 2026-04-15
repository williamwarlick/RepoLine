from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from model_stream import (
    TextStreamConfig,
    TextStreamEvent,
    build_stream_command,
    stream_text_events,
)
from provider_stream.common import (
    SentenceChunker,
    TextStreamProvider,
    _extract_codex_delta_text,
    _extract_incremental_text,
    _extract_text_candidate,
    _string_value,
    extract_text_from_content,
)
from repoline_skill import resolve_repoline_skill_prompt

ScenarioKind = Literal["provider_stream", "provider_command", "cursor_command"]
StreamEventsFactory = Callable[[TextStreamConfig], AsyncIterator[TextStreamEvent]]


@dataclass(frozen=True, slots=True)
class BenchmarkTurnSpec:
    prompt: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkScenario:
    name: str
    kind: ScenarioKind
    provider: str = "cursor"
    provider_transport: str | None = None
    provider_submit_mode: str | None = None
    working_directory: str | None = None
    prompt: str | None = None
    turns: tuple[BenchmarkTurnSpec, ...] = ()
    repeats: int = 1
    model: str | None = None
    thinking_level: str | None = None
    access_policy: str = "readonly"
    chunk_chars: int = 140
    use_repoline_prompt: bool = False
    system_prompt: str | None = None
    resume_between_turns: bool = True
    command: tuple[str, ...] | None = None
    timeout_seconds: int = 60

    def resolved_turns(self) -> tuple[BenchmarkTurnSpec, ...]:
        if self.turns:
            return self.turns
        if self.prompt is None:
            raise ValueError(f"scenario `{self.name}` is missing `prompt` or `turns`")
        return (BenchmarkTurnSpec(prompt=self.prompt),)


@dataclass(frozen=True, slots=True)
class BenchmarkPlan:
    scenarios: tuple[BenchmarkScenario, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkTurnResult:
    scenario_name: str
    scenario_kind: ScenarioKind
    repeat_index: int
    turn_index: int
    prompt: str
    turn_label: str | None
    command: tuple[str, ...] | None
    working_directory: str | None
    first_status_ms: float | None
    first_status_message: str | None
    first_assistant_ms: float | None
    first_assistant_preview: str | None
    first_response_ms: float | None
    first_response_preview: str | None
    first_speech_chunk_ms: float | None
    first_speech_chunk_preview: str | None
    completed_ms: float
    exit_code: int | None
    session_id: str | None
    error_message: str | None
    status_count: int
    speech_chunk_count: int
    line_count: int


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    turn_count: int
    mean_first_status_ms: float | None
    mean_first_assistant_ms: float | None
    mean_first_response_ms: float | None
    mean_first_speech_chunk_ms: float | None
    mean_completed_ms: float


@dataclass(frozen=True, slots=True)
class BenchmarkScenarioResult:
    scenario: BenchmarkScenario
    turns: tuple[BenchmarkTurnResult, ...]
    summary: BenchmarkSummary


def load_benchmark_plan(
    path: str | Path,
    *,
    working_directory: str | Path | None = None,
) -> BenchmarkPlan:
    plan_path = Path(path).expanduser()
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    defaults = payload.get("defaults", {})
    scenarios_payload = payload.get("scenarios")

    if not isinstance(defaults, dict):
        raise ValueError("`defaults` must be a JSON object when present")
    if not isinstance(scenarios_payload, list) or not scenarios_payload:
        raise ValueError("`scenarios` must be a non-empty JSON array")

    base_directory = Path(working_directory or os.getcwd()).expanduser().resolve()
    scenarios = tuple(
        _parse_scenario(item, defaults=defaults, base_directory=base_directory)
        for item in scenarios_payload
    )
    return BenchmarkPlan(scenarios=scenarios)


def _parse_scenario(
    payload: Any,
    *,
    defaults: dict[str, Any],
    base_directory: Path,
) -> BenchmarkScenario:
    if not isinstance(payload, dict):
        raise ValueError("Each scenario must be a JSON object")

    merged = {**defaults, **payload}
    name = _require_string(merged, "name")
    kind = _require_literal(
        merged, "kind", {"provider_stream", "provider_command", "cursor_command"}
    )
    provider = _optional_string(merged, "provider") or "cursor"
    prompt = _optional_string(merged, "prompt")
    turns = _parse_turns(merged.get("turns"))
    repeats = _optional_int(merged, "repeats", default=1)
    if repeats < 1:
        raise ValueError(f"scenario `{name}` must have repeats >= 1")

    working_directory = _optional_string(merged, "working_directory")
    resolved_workdir = (
        str((base_directory / working_directory).resolve())
        if working_directory and not Path(working_directory).is_absolute()
        else working_directory
    )

    command = _parse_command(merged.get("command"))
    if command and kind not in {"provider_command", "cursor_command"}:
        raise ValueError(
            f"scenario `{name}` only supports `command` with `provider_command`"
        )

    return BenchmarkScenario(
        name=name,
        kind=kind,
        provider=provider,
        provider_transport=_optional_string(merged, "provider_transport"),
        provider_submit_mode=_optional_string(merged, "provider_submit_mode"),
        working_directory=resolved_workdir,
        prompt=prompt,
        turns=turns,
        repeats=repeats,
        model=_optional_string(merged, "model"),
        thinking_level=_optional_string(merged, "thinking_level"),
        access_policy=_optional_string(merged, "access_policy") or "readonly",
        chunk_chars=_optional_int(merged, "chunk_chars", default=140),
        use_repoline_prompt=bool(merged.get("use_repoline_prompt", False)),
        system_prompt=_optional_string(merged, "system_prompt"),
        resume_between_turns=bool(merged.get("resume_between_turns", True)),
        command=command,
        timeout_seconds=_optional_int(merged, "timeout_seconds", default=60),
    )


def _parse_turns(value: Any) -> tuple[BenchmarkTurnSpec, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not value:
        raise ValueError("`turns` must be a non-empty array when provided")

    turns: list[BenchmarkTurnSpec] = []
    for entry in value:
        if isinstance(entry, str):
            prompt = entry.strip()
            if not prompt:
                raise ValueError("turn prompts must be non-empty strings")
            turns.append(BenchmarkTurnSpec(prompt=prompt))
            continue
        if not isinstance(entry, dict):
            raise ValueError("turns entries must be strings or objects")
        prompt = _require_string(entry, "prompt")
        turns.append(
            BenchmarkTurnSpec(prompt=prompt, label=_optional_string(entry, "label"))
        )
    return tuple(turns)


def _parse_command(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) for item in value)
    ):
        raise ValueError("`command` must be a non-empty array of strings")
    return tuple(item for item in value if item)


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = _optional_string(payload, key)
    if value is None:
        raise ValueError(f"`{key}` must be a non-empty string")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"`{key}` must be a string")
    stripped = value.strip()
    return stripped or None


def _optional_int(payload: dict[str, Any], key: str, *, default: int) -> int:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, int):
        raise ValueError(f"`{key}` must be an integer")
    return value


def _require_literal(payload: dict[str, Any], key: str, allowed: set[str]) -> str:
    value = _require_string(payload, key)
    if value not in allowed:
        supported = ", ".join(sorted(allowed))
        raise ValueError(f"`{key}` must be one of: {supported}")
    return value


def build_scenario_config(
    scenario: BenchmarkScenario,
    *,
    prompt: str,
    resume_session_id: str | None = None,
) -> TextStreamConfig:
    if scenario.working_directory is None:
        raise ValueError(f"scenario `{scenario.name}` is missing `working_directory`")

    system_prompt = scenario.system_prompt
    if scenario.use_repoline_prompt:
        system_prompt = resolve_repoline_skill_prompt(
            provider=scenario.provider,
            working_directory=scenario.working_directory,
            explicit_system_prompt=scenario.system_prompt,
        ).prompt

    return TextStreamConfig(
        prompt=prompt,
        provider=scenario.provider,  # type: ignore[arg-type]
        provider_transport=scenario.provider_transport,  # type: ignore[arg-type]
        provider_submit_mode=scenario.provider_submit_mode,
        resume_session_id=resume_session_id,
        system_prompt=system_prompt,
        model=scenario.model,
        thinking_level=scenario.thinking_level,
        working_directory=scenario.working_directory,
        chunk_chars=scenario.chunk_chars,
        access_policy=scenario.access_policy,  # type: ignore[arg-type]
    )


async def measure_provider_stream_turn(
    config: TextStreamConfig,
    *,
    scenario_name: str,
    repeat_index: int,
    turn_index: int,
    turn_label: str | None = None,
    stream_events: StreamEventsFactory = stream_text_events,
) -> BenchmarkTurnResult:
    started_at = time.perf_counter()
    first_status_ms: float | None = None
    first_status_message: str | None = None
    first_assistant_ms: float | None = None
    first_assistant_preview: str | None = None
    first_speech_chunk_ms: float | None = None
    first_speech_chunk_preview: str | None = None
    session_id = config.resume_session_id
    error_message: str | None = None
    exit_code: int | None = None
    status_count = 0
    speech_chunk_count = 0

    async for event in stream_events(config):
        elapsed_ms = _elapsed_ms(started_at)
        if event.session_id:
            session_id = event.session_id

        if event.type == "status":
            status_count += 1
            if first_status_ms is None:
                first_status_ms = elapsed_ms
                first_status_message = event.message
            continue

        if event.type == "assistant_delta" and event.text:
            if first_assistant_ms is None:
                first_assistant_ms = elapsed_ms
                first_assistant_preview = _preview_text(event.text)
            continue

        if event.type == "speech_chunk" and event.text:
            speech_chunk_count += 1
            if first_speech_chunk_ms is None:
                first_speech_chunk_ms = elapsed_ms
                first_speech_chunk_preview = _preview_text(event.text)
            continue

        if event.type == "error":
            error_message = event.message
            exit_code = event.exit_code
            continue

        if event.type == "done":
            exit_code = event.exit_code

    completed_ms = _elapsed_ms(started_at)
    return BenchmarkTurnResult(
        scenario_name=scenario_name,
        scenario_kind="provider_stream",
        repeat_index=repeat_index,
        turn_index=turn_index,
        prompt=config.prompt,
        turn_label=turn_label,
        command=tuple(build_stream_command(config)),
        working_directory=config.working_directory,
        first_status_ms=first_status_ms,
        first_status_message=first_status_message,
        first_assistant_ms=first_assistant_ms,
        first_assistant_preview=first_assistant_preview,
        first_response_ms=first_speech_chunk_ms or first_assistant_ms,
        first_response_preview=first_speech_chunk_preview or first_assistant_preview,
        first_speech_chunk_ms=first_speech_chunk_ms,
        first_speech_chunk_preview=first_speech_chunk_preview,
        completed_ms=completed_ms,
        exit_code=exit_code,
        session_id=session_id,
        error_message=error_message,
        status_count=status_count,
        speech_chunk_count=speech_chunk_count,
        line_count=0,
    )


class ProviderCommandAccumulator:
    def __init__(self, *, provider: TextStreamProvider, chunk_chars: int) -> None:
        self._provider = provider
        self._chunker = SentenceChunker(chunk_chars)
        self._assistant_text = ""
        self.session_id: str | None = None
        self.first_status_ms: float | None = None
        self.first_status_message: str | None = None
        self.first_assistant_ms: float | None = None
        self.first_assistant_preview: str | None = None
        self.first_speech_chunk_ms: float | None = None
        self.first_speech_chunk_preview: str | None = None
        self.error_message: str | None = None
        self.status_count = 0
        self.speech_chunk_count = 0
        self.line_count = 0

    @property
    def first_response_ms(self) -> float | None:
        return self.first_speech_chunk_ms or self.first_assistant_ms

    @property
    def first_response_preview(self) -> str | None:
        return self.first_speech_chunk_preview or self.first_assistant_preview

    def observe_line(self, line: str, *, elapsed_ms: float) -> None:
        self.line_count += 1

        if self._provider == "openclaw":
            self._observe_openclaw_line(line, elapsed_ms=elapsed_ms)
            return

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return

        if self._provider == "cursor":
            self._observe_cursor_event(event, elapsed_ms=elapsed_ms)
            return
        if self._provider == "gemini":
            self._observe_gemini_event(event, elapsed_ms=elapsed_ms)
            return
        if self._provider == "codex":
            self._observe_codex_event(event, elapsed_ms=elapsed_ms)
            return
        self._observe_claude_event(event, elapsed_ms=elapsed_ms)

    def _observe_openclaw_line(self, line: str, *, elapsed_ms: float) -> None:
        stripped = line.strip()
        if not stripped:
            return

        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            event = None

        if isinstance(event, dict):
            self._observe_openclaw_json(event, elapsed_ms=elapsed_ms)
            return

        if stripped.startswith("[agent/embedded] embedded run start"):
            self._mark_status("OpenClaw started a session.", elapsed_ms=elapsed_ms)
            return

        if stripped.startswith("[agent/embedded] embedded run agent start"):
            self._mark_status("OpenClaw accepted the turn.", elapsed_ms=elapsed_ms)
            return

        if stripped.startswith("["):
            return

        if stripped.startswith(("│", "◇", "├", "╰", "╯", "╭", "╮")):
            return

        if stripped.startswith(("Updated ", "Default model:", "Docs:")):
            return

        self._consume_assistant_text(stripped, elapsed_ms=elapsed_ms)

    def _observe_openclaw_json(
        self, event: dict[str, Any], *, elapsed_ms: float
    ) -> None:
        meta = event.get("meta")
        if isinstance(meta, dict):
            agent_meta = meta.get("agentMeta")
            if isinstance(agent_meta, dict):
                self.session_id = (
                    _string_value(agent_meta.get("sessionId")) or self.session_id
                )

        payloads = event.get("payloads")
        if isinstance(payloads, list):
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                text = _string_value(payload.get("text"))
                if text:
                    self._consume_assistant_text(text, elapsed_ms=elapsed_ms)
            self._flush_chunks(elapsed_ms=elapsed_ms)

    def _observe_cursor_event(
        self, event: dict[str, Any], *, elapsed_ms: float
    ) -> None:
        session_id = _string_value(event.get("session_id"))
        if session_id:
            self.session_id = session_id

        event_type = _string_value(event.get("type"))
        if event_type == "system" and _string_value(event.get("subtype")) == "init":
            self._mark_status("Cursor Agent started a session.", elapsed_ms=elapsed_ms)
            return

        if event_type == "assistant":
            message = event.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                text = extract_text_from_content(content, preserve_whitespace=True)
            else:
                text = _extract_text_candidate(message) or ""
            self._consume_assistant_text(text, elapsed_ms=elapsed_ms)
            return

        if event_type == "result":
            if event.get("is_error"):
                self.error_message = (
                    _string_value(event.get("result"))
                    or self.error_message
                    or "Cursor Agent failed."
                )
                return

            result_text = _string_value(event.get("result")) or ""
            self._consume_assistant_text(result_text, elapsed_ms=elapsed_ms)
            self._flush_chunks(elapsed_ms=elapsed_ms)

    def _observe_gemini_event(
        self, event: dict[str, Any], *, elapsed_ms: float
    ) -> None:
        session_id = _string_value(event.get("session_id"))
        if session_id:
            self.session_id = session_id

        event_type = _string_value(event.get("type"))
        if event_type == "init":
            self._mark_status("Gemini CLI started a session.", elapsed_ms=elapsed_ms)
            return

        if event_type == "message" and _string_value(event.get("role")) == "assistant":
            text = (
                _extract_text_candidate(event.get("content"))
                or _string_value(event.get("content"))
                or _extract_text_candidate(event)
                or ""
            )
            self._consume_assistant_text(text, elapsed_ms=elapsed_ms)
            return

        if event_type == "result":
            status = _string_value(event.get("status")) or "success"
            if status != "success":
                self.error_message = self.error_message or f"Gemini CLI failed with status {status}."
                return
            self._flush_chunks(elapsed_ms=elapsed_ms)

    def _observe_codex_event(
        self, event: dict[str, Any], *, elapsed_ms: float
    ) -> None:
        event_type = _string_value(event.get("type"))
        if event_type == "thread.started":
            self.session_id = _string_value(event.get("thread_id")) or self.session_id
            self._mark_status("Codex CLI started a session.", elapsed_ms=elapsed_ms)
            return

        if event_type in {"turn.started", "task_started"}:
            self._mark_status("Codex CLI accepted the turn.", elapsed_ms=elapsed_ms)
            return

        delta_text = _extract_codex_delta_text(event)
        if delta_text:
            self._consume_assistant_text(delta_text, elapsed_ms=elapsed_ms)
            return

        if event_type == "item.completed":
            item = event.get("item", {})
            if not isinstance(item, dict):
                return
            item_type = _string_value(item.get("type"))
            if item_type == "error":
                self.error_message = (
                    _string_value(item.get("message"))
                    or self.error_message
                    or "Codex CLI failed."
                )
                return
            if item_type == "agent_message":
                self._consume_assistant_text(
                    _extract_text_candidate(item) or "",
                    elapsed_ms=elapsed_ms,
                )
                return

        if event_type in {"turn.completed", "task_complete"}:
            last_agent_message = _string_value(event.get("last_agent_message"))
            if last_agent_message:
                self._consume_assistant_text(last_agent_message, elapsed_ms=elapsed_ms)
            self._flush_chunks(elapsed_ms=elapsed_ms)

    def _observe_claude_event(
        self, event: dict[str, Any], *, elapsed_ms: float
    ) -> None:
        event_type = _string_value(event.get("type"))
        if event_type == "stream_event":
            inner = event.get("event", {})
            if not isinstance(inner, dict):
                return
            inner_type = _string_value(inner.get("type"))
            if inner_type == "message_start":
                self._mark_status("Claude Code accepted the turn.", elapsed_ms=elapsed_ms)
                return
            if inner_type == "message_stop":
                self._flush_chunks(elapsed_ms=elapsed_ms)
                return
            if inner_type == "content_block_delta":
                text = _string_value(inner.get("delta", {}).get("text"))
                if text:
                    self._consume_assistant_text(text, elapsed_ms=elapsed_ms)
                return

        if event_type == "result":
            if event.get("is_error"):
                self.error_message = (
                    _string_value(event.get("result"))
                    or self.error_message
                    or "Claude Code failed."
                )
                return
            self._flush_chunks(elapsed_ms=elapsed_ms)

    def _mark_status(self, message: str, *, elapsed_ms: float) -> None:
        self.status_count += 1
        if self.first_status_ms is None:
            self.first_status_ms = elapsed_ms
            self.first_status_message = message

    def _consume_assistant_text(self, text: str, *, elapsed_ms: float) -> None:
        delta_text = _extract_incremental_text(text, self._assistant_text)
        if not delta_text:
            return

        if self.first_assistant_ms is None:
            self.first_assistant_ms = elapsed_ms
            self.first_assistant_preview = _preview_text(delta_text)

        self._assistant_text += delta_text
        for chunk in self._chunker.feed(delta_text):
            self.speech_chunk_count += 1
            if self.first_speech_chunk_ms is None:
                self.first_speech_chunk_ms = elapsed_ms
                self.first_speech_chunk_preview = _preview_text(chunk)

    def _flush_chunks(self, *, elapsed_ms: float) -> None:
        for chunk in self._chunker.flush():
            self.speech_chunk_count += 1
            if self.first_speech_chunk_ms is None:
                self.first_speech_chunk_ms = elapsed_ms
                self.first_speech_chunk_preview = _preview_text(chunk)


CursorCommandAccumulator = ProviderCommandAccumulator


async def measure_provider_command_turn(
    *,
    provider: TextStreamProvider,
    scenario_kind: ScenarioKind,
    scenario_name: str,
    prompt: str,
    command: Sequence[str],
    working_directory: str | None,
    chunk_chars: int,
    repeat_index: int,
    turn_index: int,
    turn_label: str | None = None,
) -> BenchmarkTurnResult:
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=working_directory or None,
        env=os.environ.copy(),
        start_new_session=True,
    )
    if proc.stdout is not None:
        proc.stdout._limit = max(proc.stdout._limit, 1024 * 1024)  # type: ignore[attr-defined]

    accumulator = ProviderCommandAccumulator(provider=provider, chunk_chars=chunk_chars)
    started_at = time.perf_counter()

    try:
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            accumulator.observe_line(line, elapsed_ms=_elapsed_ms(started_at))
    except asyncio.CancelledError:
        await _terminate_process_tree(proc)
        raise

    exit_code = await proc.wait()
    completed_ms = _elapsed_ms(started_at)

    return BenchmarkTurnResult(
        scenario_name=scenario_name,
        scenario_kind=scenario_kind,
        repeat_index=repeat_index,
        turn_index=turn_index,
        prompt=prompt,
        turn_label=turn_label,
        command=tuple(command),
        working_directory=working_directory,
        first_status_ms=accumulator.first_status_ms,
        first_status_message=accumulator.first_status_message,
        first_assistant_ms=accumulator.first_assistant_ms,
        first_assistant_preview=accumulator.first_assistant_preview,
        first_response_ms=(
            accumulator.first_speech_chunk_ms or accumulator.first_assistant_ms
        ),
        first_response_preview=(
            accumulator.first_speech_chunk_preview
            or accumulator.first_assistant_preview
        ),
        first_speech_chunk_ms=accumulator.first_speech_chunk_ms,
        first_speech_chunk_preview=accumulator.first_speech_chunk_preview,
        completed_ms=completed_ms,
        exit_code=exit_code,
        session_id=accumulator.session_id,
        error_message=accumulator.error_message,
        status_count=accumulator.status_count,
        speech_chunk_count=accumulator.speech_chunk_count,
        line_count=accumulator.line_count,
    )


measure_cursor_command_turn = measure_provider_command_turn


async def run_benchmark_plan(
    plan: BenchmarkPlan,
) -> tuple[BenchmarkScenarioResult, ...]:
    return tuple(
        [await run_benchmark_scenario(scenario) for scenario in plan.scenarios]
    )


async def run_benchmark_scenario(
    scenario: BenchmarkScenario,
) -> BenchmarkScenarioResult:
    turn_results: list[BenchmarkTurnResult] = []

    for repeat_index in range(1, scenario.repeats + 1):
        resume_session_id: str | None = None

        for turn_index, turn in enumerate(scenario.resolved_turns(), start=1):
            if scenario.kind == "provider_stream":
                config = build_scenario_config(
                    scenario,
                    prompt=turn.prompt,
                    resume_session_id=resume_session_id,
                )
                try:
                    result = await asyncio.wait_for(
                        measure_provider_stream_turn(
                            config,
                            scenario_name=scenario.name,
                            repeat_index=repeat_index,
                            turn_index=turn_index,
                            turn_label=turn.label,
                        ),
                        timeout=scenario.timeout_seconds,
                    )
                except TimeoutError:
                    result = _timeout_result(
                        scenario=scenario,
                        prompt=turn.prompt,
                        repeat_index=repeat_index,
                        turn_index=turn_index,
                        turn_label=turn.label,
                        command=tuple(build_stream_command(config)),
                    )
            else:
                if scenario.command is not None and turn_index > 1:
                    raise ValueError(
                        f"scenario `{scenario.name}` cannot use `command` with multi-turn resume"
                    )
                if scenario.command is not None:
                    command = list(scenario.command)
                else:
                    config = build_scenario_config(
                        scenario,
                        prompt=turn.prompt,
                        resume_session_id=resume_session_id,
                    )
                    command = build_stream_command(config)
                try:
                    result = await asyncio.wait_for(
                        measure_provider_command_turn(
                            provider=scenario.provider,  # type: ignore[arg-type]
                            scenario_kind=scenario.kind,
                            scenario_name=scenario.name,
                            prompt=turn.prompt,
                            command=command,
                            working_directory=scenario.working_directory,
                            chunk_chars=scenario.chunk_chars,
                            repeat_index=repeat_index,
                            turn_index=turn_index,
                            turn_label=turn.label,
                        ),
                        timeout=scenario.timeout_seconds,
                    )
                except TimeoutError:
                    result = _timeout_result(
                        scenario=scenario,
                        prompt=turn.prompt,
                        repeat_index=repeat_index,
                        turn_index=turn_index,
                        turn_label=turn.label,
                        command=tuple(command),
                    )

            turn_results.append(result)
            if scenario.resume_between_turns and result.session_id:
                resume_session_id = result.session_id

    return BenchmarkScenarioResult(
        scenario=scenario,
        turns=tuple(turn_results),
        summary=summarize_turn_results(turn_results),
    )


def _timeout_result(
    *,
    scenario: BenchmarkScenario,
    prompt: str,
    repeat_index: int,
    turn_index: int,
    turn_label: str | None,
    command: tuple[str, ...] | None,
) -> BenchmarkTurnResult:
    timeout_ms = float(scenario.timeout_seconds * 1000)
    return BenchmarkTurnResult(
        scenario_name=scenario.name,
        scenario_kind=scenario.kind,
        repeat_index=repeat_index,
        turn_index=turn_index,
        prompt=prompt,
        turn_label=turn_label,
        command=command,
        working_directory=scenario.working_directory,
        first_status_ms=None,
        first_status_message=None,
        first_assistant_ms=None,
        first_assistant_preview=None,
        first_response_ms=None,
        first_response_preview=None,
        first_speech_chunk_ms=None,
        first_speech_chunk_preview=None,
        completed_ms=timeout_ms,
        exit_code=None,
        session_id=None,
        error_message=f"Timed out after {scenario.timeout_seconds}s.",
        status_count=0,
        speech_chunk_count=0,
        line_count=0,
    )


def summarize_turn_results(turns: Iterable[BenchmarkTurnResult]) -> BenchmarkSummary:
    turn_list = list(turns)
    if not turn_list:
        raise ValueError("cannot summarize an empty benchmark result set")

    return BenchmarkSummary(
        turn_count=len(turn_list),
        mean_first_status_ms=_mean(result.first_status_ms for result in turn_list),
        mean_first_assistant_ms=_mean(
            result.first_assistant_ms for result in turn_list
        ),
        mean_first_response_ms=_mean(
            result.first_response_ms for result in turn_list
        ),
        mean_first_speech_chunk_ms=_mean(
            result.first_speech_chunk_ms for result in turn_list
        ),
        mean_completed_ms=_mean(
            result.completed_ms
            for result in turn_list
            if result.completed_ms is not None
        )
        or 0.0,
    )


def results_to_json(
    results: Sequence[BenchmarkScenarioResult],
) -> str:
    return json.dumps(
        [_scenario_result_to_dict(result) for result in results], indent=2
    )


def format_results(results: Sequence[BenchmarkScenarioResult]) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(f"Scenario: {result.scenario.name} ({result.scenario.kind})")
        lines.append("turn  repeat  status    assistant  response  done      preview")
        for turn in result.turns:
            preview = (
                turn.first_response_preview
                or turn.first_speech_chunk_preview
                or turn.first_assistant_preview
                or "-"
            )
            lines.append(
                f"{turn.turn_index:<5} "
                f"{turn.repeat_index:<7} "
                f"{_format_ms(turn.first_status_ms):<9} "
                f"{_format_ms(turn.first_assistant_ms):<10} "
                f"{_format_ms(turn.first_response_ms):<9} "
                f"{_format_ms(turn.completed_ms):<9} "
                f"{preview}"
            )
            if turn.error_message:
                lines.append(f"error: {turn.error_message}")
        lines.append(
            "summary: "
            f"mean response={_format_ms(result.summary.mean_first_response_ms)}, "
            f"mean assistant={_format_ms(result.summary.mean_first_assistant_ms)}, "
            f"mean done={_format_ms(result.summary.mean_completed_ms)}"
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def _scenario_result_to_dict(result: BenchmarkScenarioResult) -> dict[str, Any]:
    return {
        "scenario": asdict(result.scenario),
        "turns": [asdict(turn) for turn in result.turns],
        "summary": asdict(result.summary),
    }


def _preview_text(value: str, *, limit: int = 96) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _mean(values: Iterable[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 1)


def _format_ms(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}ms"


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 1)


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2)
        return
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def _terminate_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    try:
        os.killpg(proc.pid, 15)
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=2)
        return
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, 9)
        except ProcessLookupError:
            return
        await proc.wait()
