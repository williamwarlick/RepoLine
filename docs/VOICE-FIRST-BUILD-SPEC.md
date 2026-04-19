# RepoLine Voice-First Build Spec

Date: 2026-04-17
Status: Proposed

## Summary

RepoLine should support two first-class execution modes:

- `direct`: the current mode, where one configured coding CLI is the assistant on the call
- `orchestrated`: a new voice-first mode, where a low-latency orchestrator handles the live conversation and delegates bounded work to coding CLIs as workers

The new mode must not replace the direct providers. It must sit on top of them, use the same provider adapters where possible, and remain directly comparable against `claude`, `codex`, `cursor`, and `gemini` in latency and task-quality benchmarks.

In plain terms: yes, the new option is a voice-first agent that can call the direct coding CLIs as subagents or workers. The important constraint is that RepoLine must still be able to run those direct CLIs head-to-head without the orchestrator in the loop.

## Why This Exists

The current bridge is strong at transport and telephony, but the live call path is still tied too closely to the latency profile of the backing coding CLI. The repo already separates those responsibilities:

- LiveKit owns transport, STT, TTS, and telephony.
- RepoLine owns turn coordination and spoken chunking.
- The coding CLI owns reasoning, tool use, and repo state.

That split is described in [HOW-IT-WORKS.md](./HOW-IT-WORKS.md). The latency notes in [LATENCY.md](./LATENCY.md) also show that the main tax is often CLI startup and orchestration rather than the speech layer itself.

The new mode keeps the current strengths while moving the live conversation onto a faster control plane.

## Product Thesis

RepoLine should become a voice operating layer for coding work, not just a phone wrapper around one CLI process.

That means:

- phone or browser voice stays the primary interface
- the first spoken response is optimized for low latency and continuity
- coding CLIs become pluggable workers behind that interface
- the browser companion remains the precision surface for diffs, artifacts, and approvals
- direct provider mode remains available for comparison, benchmarking, and users who prefer raw provider behavior

## Goals

- Preserve the current `direct` mode with minimal disruption.
- Add an `orchestrated` mode that feels faster and more conversational on the phone.
- Keep `claude`, `codex`, `cursor`, and `gemini` usable as direct backends and orchestrated workers.
- Reuse the existing provider stream adapter layer instead of creating a second incompatible integration stack.
- Support safe voice-driven coding with explicit mutation approval checkpoints.
- Produce benchmarkable comparisons between direct and orchestrated execution.

## Non-Goals

- Replacing the existing provider adapters.
- Hiding direct provider behavior behind one merged score or opaque abstraction.
- Making every turn multi-agent by default.
- Performing destructive repo actions without an explicit approval flow.
- Shipping a cloud-hosted coding runtime in this phase.

## Execution Modes

### `direct`

This is the current behavior:

- one configured provider handles the turn end to end
- provider output is streamed back to speech when available
- RepoLine acts as transport and coordination glue

This mode remains the benchmark baseline.

### `orchestrated`

This is the new behavior:

- a low-latency orchestrator owns the live conversation
- the orchestrator can answer short control turns itself
- the orchestrator dispatches repo work to one primary coding worker
- the orchestrator may launch optional sidecar workers for non-blocking subtasks
- the orchestrator summarizes progress and results back to the caller

This mode is the product bet for high-quality phone-first coding.

## Architecture

### Existing modules to preserve

- [agent/src/agent.py](../agent/src/agent.py): LiveKit session setup, STT, TTS, turn handling, room integration
- [agent/src/turn_coordinator.py](../agent/src/turn_coordinator.py): turn lifecycle, pending transcripts, speech output, provider event handling
- [agent/src/provider_stream/adapter.py](../agent/src/provider_stream/adapter.py): provider adapter facade for `claude`, `codex`, `cursor`, and `gemini`
- [agent/src/bridge_config.py](../agent/src/bridge_config.py): environment-driven runtime config
- [frontend/app/api/token/route.ts](../frontend/app/api/token/route.ts): browser session token minting

### New modules to add

- `agent/src/orchestrator_policy.py`
  - deterministic routing policy for turn classification
  - initial version should be rule-based, not model-based
- `agent/src/orchestrator_runtime.py`
  - orchestrated turn executor
  - handles fast acknowledgments, worker dispatch, and progress narration
- `agent/src/worker_pool.py`
  - persistent worker/session manager keyed by provider and workdir
  - hides warm versus cold worker differences
- `agent/src/task_modes.py`
  - shared typed definitions for task kinds and approval requirements
- `agent/src/approval_state.py`
  - state machine for voice/browser approval checkpoints
- `agent/src/orchestrator_metrics.py`
  - orchestrator-specific telemetry helpers layered on top of existing bridge telemetry

### Optional later modules

- `agent/src/orchestrator_llm.py`
  - optional semantic router for ambiguous voice turns
  - should be disabled by default in the first implementation
- `agent/src/sidecar_dispatch.py`
  - limited parallel worker dispatch for bounded non-blocking subtasks

## Core Runtime Model

### Hot path

The hot path must stay simple:

1. user finishes speaking
2. RepoLine gets a final transcript from LiveKit
3. orchestrator classifies the turn
4. orchestrator speaks a fast acknowledgment or direct answer
5. orchestrator either completes the turn or dispatches work to a worker
6. worker results stream back as short spoken updates and browser artifacts

The hot path should not wait for a full coding worker turn before speaking.

### Cold path

The coding worker path handles:

- repo inspection
- code changes
- tests
- git operations
- long explanations
- tool-heavy workflows

This work can take longer, but the caller should hear progress before it finishes.

## Task Modes

Every incoming turn in `orchestrated` mode must be classified into one of these modes:

- `answer`
  - short factual answer from current conversation or cached repo context
  - no worker call required
- `clarify`
  - ask one short question before doing work
- `inspect`
  - look around the repo and report findings
  - read-only worker task
- `patch`
  - propose or make code changes
  - requires approval before mutation if access policy is not already elevated
- `verify`
  - run tests, typechecks, benchmarks, or browser verification
- `background_task`
  - long-running task that should continue while the caller stays informed
- `handoff`
  - switch the primary worker provider for this task
- `approval_required`
  - explicit approval gate before a sensitive action

## Provider Strategy

Providers remain first-class citizens in both modes.

### Direct mode

- `claude`, `codex`, `cursor`, `gemini`
- current behavior remains intact

### Orchestrated mode

The orchestrator can choose a worker backend based on task shape:

- `cursor`
  - strong for repo-coupled IDE-style work
- `codex`
  - strong for structured coding and patch tasks
- `claude`
  - strong when partial text streaming quality matters
- `gemini`
  - strong for low-latency voice-side reasoning, especially via direct API transport

RepoLine should support:

- a default primary worker
- per-task worker overrides
- optional sidecar workers for bounded tasks such as parallel inspection or isolated verification

This keeps the new architecture competitive with direct provider use instead of replacing it with one universal stack.

## Orchestrator Design

### Phase 1: deterministic orchestrator

The first implementation should not add a second always-on LLM dependency.

Instead, it should use:

- turn source: voice transcript or browser chat
- lightweight heuristics
- current access policy
- conversation-local state
- optional cached repo summary

It can reliably decide:

- whether to answer directly
- whether to ask for clarification
- whether work is read-only or mutating
- whether the user needs an immediate spoken acknowledgment

### Phase 2: optional semantic router

A later version may add a very fast model-backed router for ambiguous intent classification. That router must be:

- optional
- benchmarked against the deterministic baseline
- removable without breaking orchestrated mode

## Worker Model

Workers are not the same as the live voice orchestrator.

Workers are provider-backed coding executors with persistent session state where supported.

### Worker requirements

- keyed by `provider + workdir + access_policy`
- able to stay warm across multiple turns
- expose `submit`, `interrupt`, `resume`, and `shutdown`
- surface partial text, status, and artifacts through the existing adapter/event model
- avoid paying full cold-start cost on every turn when the backend supports persistence

### Worker contract

Each worker should expose:

- `submit(task)`
- `stream_events()`
- `interrupt()`
- `can_resume`
- `last_session_id`
- `warm_state`

Where possible, the worker pool should wrap the existing provider stream facade instead of bypassing it.

## Sidecar Worker Rules

Sidecars are optional and must be tightly constrained.

Use sidecars only for:

- independent codebase search
- isolated verification
- alternative-solution exploration
- disjoint implementation slices

Do not use sidecars for:

- the first spoken response
- tasks that block the next required spoken update
- mutating overlapping files without explicit coordination

The primary worker remains the owner of the main task. Sidecars feed findings or artifacts back to the orchestrator.

## Approval Model

Voice-first coding is unsafe without explicit control points.

RepoLine should keep:

- `readonly` as the safe default for phone-first usage
- spoken confirmation for sensitive actions
- browser companion approval for high-precision actions when available
- optional DTMF confirmation for phone-only flows

Actions that require approval:

- file mutation
- package installation
- test commands with side effects
- git stage, commit, push, branch creation
- deploy or external service mutation

Approval state must survive interruptions and be visible in the browser companion.

## Browser Companion Requirements

The browser UI becomes more important in `orchestrated` mode.

It should be used for:

- transcript and status
- artifact cards
- file references
- diff previews
- approvals
- worker selection and mode display

RepoLine should keep the phone path usable on its own, but the browser companion is the preferred precision surface.

## Configuration Additions

Add the following environment variables in a backward-compatible way:

- `BRIDGE_EXECUTION_MODE=direct|orchestrated`
- `BRIDGE_PRIMARY_WORKER_PROVIDER=<provider>`
- `BRIDGE_ENABLE_SIDECARS=true|false`
- `BRIDGE_MAX_SIDECARS=<int>`
- `BRIDGE_REQUIRE_APPROVAL_FOR_PATCH=true|false`
- `BRIDGE_REQUIRE_APPROVAL_FOR_GIT=true|false`
- `BRIDGE_ORCHESTRATOR_PROGRESS_DELAY_SECONDS=<float>`
- `BRIDGE_ORCHESTRATOR_FAST_ACK=true|false`

Optional later settings:

- `BRIDGE_ORCHESTRATOR_ROUTER=rule|model`
- `BRIDGE_ORCHESTRATOR_MODEL=<model>`

Defaults should preserve current behavior:

- `BRIDGE_EXECUTION_MODE=direct`
- sidecars disabled
- approval required for mutation in orchestrated mode

## Telemetry Requirements

The benchmark and report work already in flight should remain the source of truth for comparison outputs. This spec adds the event model those tools should consume.

New orchestrator telemetry should record:

- `orchestrator_turn_opened`
- `orchestrator_task_mode_selected`
- `orchestrator_fast_ack_started`
- `orchestrator_fast_ack_completed`
- `worker_dispatch_started`
- `worker_dispatch_completed`
- `worker_first_status`
- `worker_first_delta`
- `worker_first_artifact`
- `approval_requested`
- `approval_granted`
- `approval_denied`
- `sidecar_started`
- `sidecar_completed`
- `orchestrator_turn_completed`

Critical latency fields:

- `final_transcript_to_fast_ack_ms`
- `final_transcript_to_route_decision_ms`
- `final_transcript_to_worker_start_ms`
- `worker_start_to_first_delta_ms`
- `final_transcript_to_first_spoken_result_ms`
- `interrupt_to_recovery_ms`

## Benchmark Compatibility

This architecture must integrate with the benchmark work, not compete with it.

The benchmark matrix should support at least:

- direct `cursor` versus orchestrated `cursor-worker`
- direct `codex` versus orchestrated `codex-worker`
- direct `gemini api` versus orchestrated `gemini-primary`
- orchestrated mixed setups such as `gemini-orchestrator + codex-worker`
- orchestrated mixed setups such as `gemini-orchestrator + cursor-worker`

Representative scenarios:

- one-line answer
- repo summary
- inspect one file
- find root cause
- propose patch plan
- apply small patch after approval
- run one verification command

The orchestrated mode should only count as a win if it improves user-visible voice performance without causing a material drop in task success.

## Testing Strategy

### Unit tests

Add tests for:

- task mode classification
- approval state transitions
- worker selection policy
- sidecar eligibility rules
- interruption and recovery behavior

Proposed test files:

- `agent/tests/test_orchestrator_policy.py`
- `agent/tests/test_worker_pool.py`
- `agent/tests/test_approval_state.py`
- `agent/tests/test_orchestrator_runtime.py`

### Integration tests

Add fake provider-stream tests for:

- fast acknowledgment before worker completion
- worker handoff after classification
- worker interruption mid-stream
- approval pause and resume
- sidecar completion without blocking primary narration

### End-to-end verification

Validate in both browser and phone paths:

- no dead air over 2 seconds without a cue or spoken progress update
- direct mode still behaves exactly as expected
- orchestrated mode gives earlier spoken feedback on inspect and patch tasks
- browser artifacts stay aligned with spoken progress

## Success Criteria

### Voice quality

- first spoken acknowledgment under 700 ms for common turns
- first spoken progress update under 3 s for repo tasks
- interruption recovery that feels immediate and does not lose task state

### Coding quality

- no regression in direct mode
- orchestrated mode matches direct mode on small-task correctness
- orchestrated mode improves perceived responsiveness on phone-first tasks

### Safety

- mutating actions never execute without passing the approval state machine
- browser and voice approval state stay consistent

## Build Phases

### Phase 0

- keep current direct mode as baseline
- consume the benchmark/report tooling work already underway

### Phase 1

- add execution mode plumbing
- add deterministic orchestrator policy
- add orchestrator telemetry
- no sidecars yet

### Phase 2

- add persistent worker pool
- keep one primary worker only
- validate warm-session gains

### Phase 3

- add approval state machine and browser approval surface
- enable safe patch workflows

### Phase 4

- add optional sidecars for bounded read-only tasks
- benchmark carefully against the primary-worker baseline

### Phase 5

- optional model-backed semantic router
- only if deterministic routing leaves too many ambiguous turns

## Initial Implementation Slice

The first slice should be small and benchmarkable:

1. add `BRIDGE_EXECUTION_MODE`
2. add deterministic task classification
3. add fast spoken acknowledgment
4. dispatch read-only `inspect` tasks to one primary worker
5. stream status and artifacts back through the existing event path
6. compare direct versus orchestrated on the same read-only scenarios

Do not start with sidecars or mutating patch flows.

## Open Questions

- Should the orchestrator ever have its own model identity to the user, or should it stay invisible and present only the selected worker?
- Should phone-only approval rely on speech, DTMF, or both?
- Which provider should be the default primary worker for orchestrated mode?
- Does Cursor App transport belong in the worker pool immediately, or only after CLI-backed workers stabilize?

## Recommendation

Build `orchestrated` mode as an additive layer on top of the current direct-provider architecture.

The concrete product should be:

- a voice-first orchestrator for the live call
- one primary coding worker behind it
- optional sidecars later
- direct mode preserved forever as a benchmark and user-facing option

That gives RepoLine a stronger phone-first experience without losing the ability to plug in, compare, and compete with the direct coding agent options that already make the project useful.
