# RepoLine Goals

This page is the durable working queue for making RepoLine a codebase that agents can keep improving without rediscovering the operating model each time.

## Started Now

### 1. Single Verification Contract

Goal: every agent should know the one command that proves a change is ready.

Current state:

- `bin/check quick` runs root script tests, agent pytest, frontend lint, frontend typecheck, and frontend tests.
- `bin/check` adds the frontend production build.
- CI routes through the same local target names so local proof and remote proof stay aligned.

Next useful work:

- Add a targeted `bin/check evals` target if benchmark/report tests need their own narrower loop.
- Add a `bin/check doctor` target only if it can run without requiring private LiveKit state.

### 2. Agent Navigation Surface

Goal: a new coding agent should find the runtime modules, docs, and verification commands in under a minute.

Current state:

- `AGENTS.md` holds the root operating contract.
- `docs/agents/repo-map.md` explains where the main modules live.
- `docs/agents/testing.md` explains the quality gates.

Next useful work:

- Add deeper maps only after a repeated navigation miss, not preemptively.
- Keep this surface short enough that agents actually read it.

### 3. Cursor 2.5 Provider Upgrade

Goal: make Composer 2.5 a first-class Cursor-backed model without confusing a model promotion with a new provider path.

Current state:

- Current repo defaults still point Cursor at `composer-2-fast`.
- Current local Cursor Agent exposes `composer-2.5` and `composer-2.5-fast`.
- A read-only headless `composer-2.5-fast` smoke run succeeded on Cursor Agent CLI `2026.05.20-2b5dd59`.
- The concrete implementation and validation checklist lives in [`docs/agents/cursor-2.5-support-plan.md`](./cursor-2.5-support-plan.md).

Next useful work:

- Promote the Cursor default only after updating the Python, TypeScript, runtime model, Cursor App, docs, and benchmark surfaces named in the plan.
- Do not update public support claims until the checked-in validation note and benchmark evidence exist.

## Next Goals

### 4. Evidence-Backed Provider Support

Goal: public provider support claims stay tied to recent checked-in validation evidence.

Good first slice:

- Add a small provider-support freshness check that reads `docs/ONBOARDING.md` and fails when a validated support date is more than 90 days old.
- Keep the check advisory at first unless it is wired into a specific release workflow.

### 5. Evaluation Harness As The Improvement Loop

Goal: latency work should flow through fixed prompt sets and normalized turn records instead of ad hoc impressions.

Good first slice:

- Create a small checked-in smoke command that runs the fastest stable planning pack and writes to a scratch output path.
- Make the report reject mixed `benchmark_family`, `benchmark_revision`, or `plan_sha256` before any recommendation text is generated.

### 6. Runtime Locality

Goal: turn handling, provider streaming, and browser runtime state should stay deep enough that fixes land in one place.

Good first slice:

- Review the `TurnOrchestrator` -> `TurnCoordinator` -> provider stream path for any pass-through modules before adding more runtime modes.
- Keep `model_stream.py` as a compatibility facade only while existing callers still need it; new provider behavior should land under `agent/src/provider_stream/`.

### 7. Setup And Doctor As Product Contracts

Goal: setup and doctor should encode onboarding truth, not just print helpful text.

Good first slice:

- Add contract tests for any new setup flag before changing interactive setup.
- When docs say a mode is supported, make `bun run doctor` prove the local prerequisites or explain the exact missing state.
