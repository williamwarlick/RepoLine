# Repo Map

## Root

- `scripts/phone-bridge.ts`: top-level setup, dev, live, agent, and doctor CLI.
- `scripts/bridge-runtime-config.ts`: TypeScript runtime config and env materialization.
- `scripts/bridge-installation-contract.ts`: installation contract for RepoLine skills/rules in target repos.
- `scripts/bridge-doctor.ts`: local prerequisite and installed-skill checks.
- `scripts/latency_*.py`: latency harness, reporting, and analysis command surface.
- `skills/`: RepoLine skills installed into target coding-agent repos.
- `CONTEXT.md`: domain language for provider support, latency, evals, and hard cutovers.

## Agent Runtime

- `agent/src/agent.py`: LiveKit worker entrypoint and room/session integration.
- `agent/src/bridge_config.py`: Python runtime config loaded from generated env.
- `agent/src/turn_orchestrator.py`: narrow submit/runtime-state interface used by the LiveKit worker.
- `agent/src/turn_coordinator.py`: turn lifecycle, interruption handling, provider submission, and telemetry events.
- `agent/src/provider_stream/`: provider adapters for Claude, Codex, Cursor, Cursor App, and Gemini.
- `agent/src/telemetry.py`: JSONL telemetry and call summary generation.
- `agent/tests/`: Python regression suite for runtime behavior, providers, telemetry, and latency helpers.

## Frontend

- `frontend/app/page.tsx`: app entrypoint.
- `frontend/app/api/token/route.ts`: local token route for LiveKit rooms.
- `frontend/components/app/`: product-specific RepoLine shell and view controller.
- `frontend/components/agents-ui/`: imported/adapted LiveKit Agents UI primitives.
- `frontend/hooks/useRepolineSessionRuntime.ts`: browser-side session state and runtime model controls.
- `frontend/lib/`: access control, session state parsing, artifact parsing, thinking sound, and voice-session helpers.

## Docs And Evidence

- `docs/ONBOARDING.md`: first-run path and provider support matrix.
- `docs/HOW-IT-WORKS.md`: runtime model and state ownership.
- `docs/EVALS.md`: benchmark/eval schema and interpretation rules.
- `docs/LATENCY.md`: latency observations and current recommendations.
- `docs/PHONE.md`: telephony setup and operational requirements.
- `docs/CURSOR-APP-VALIDATION-2026-04-19.md`: checked-in Cursor App validation evidence.
- `output/latency/`: checked-in benchmark artifacts plus local scratch artifacts; do not commit new generated outputs unless they are intentionally part of a validation update.
