# Latency Notes

RepoLine's current latency work is centered on the scenario-runner harness, not on public benchmark charts.

## Current Buckets

The harness records four timing buckets per turn:

1. `provider_first_status_ms`
2. `provider_first_assistant_delta_ms`
3. `spoken_response_latency_ms`
4. `completed_turn_ms`

That gives a useful breakdown for coding-agent comparisons without pulling LiveKit phone timing into the first cut.

## What To Optimize Against

For current recommendations:

- headline metric: `spoken_response_latency_ms`
- first diagnostic: `provider_first_assistant_delta_ms`
- second diagnostic: `completed_turn_ms`
- for the fastest current Cursor-backed runtime path, prefer `BRIDGE_CURSOR_TRANSPORT=app` with submit mode `auto`
- for the simpler clean-benchmark Cursor path, prefer `BRIDGE_CURSOR_TRANSPORT=cli`
- when you want to compare `Cursor Agent` models quickly in browser sessions, use the runtime model picker in the control bar instead of restarting the bridge

If two paths have similar `spoken_response_latency_ms`, prefer the simpler and more stable one operationally.

## Thresholds

The local report flags these buckets today:

- warning: `spoken_response_latency_ms > 10s`
- severe: `spoken_response_latency_ms > 30s`
- timeout: `completed_turn_ms >= 120s`

These are not hard product SLAs. They are local comparison thresholds for deciding what feels acceptable in planning mode.

## Scope Boundary

RepoLine is a voice bridge for coding agents with local repo access.

That means:

- `Gemini CLI` is in scope
- the non-coding Gemini transport is out of scope and removed from the product surface
- `Cursor App` is a validated runtime path, but it remains version-sensitive

For current `Cursor Agent` CLI builds in readonly mode, the harness uses Cursor's read-only `ask` mode instead of forcing `--sandbox enabled`, because that sandbox mode can be unavailable on some systems.

For current `Cursor App` builds, the recommended app submit mode is `auto`, which now prefers the stable direct input path when Cursor's bridge reports that composer-handle submission is unavailable. Explicit bridge-handle submission remains useful only as a diagnostic mode.

For current Cursor-backed browser sessions, runtime model control is split intentionally:

- `Cursor Agent` CLI can switch models live for subsequent turns from the RepoLine control bar
- `Cursor App` can switch between the supported runtime models from the RepoLine control bar by updating Cursor's local composer state

The current runtime evidence is summarized in [`docs/CURSOR-APP-VALIDATION-2026-04-19.md`](./CURSOR-APP-VALIDATION-2026-04-19.md). In that validation pass, the app path beat headless Cursor across the tested fresh and warm turns.

The current benchmark caveat is fresh-session isolation: on the tested Cursor desktop build, `composer.createNew` appends a new composer id to bridge state but does not reliably move `selectedComposerId`, so strict fresh-composer benchmarking is not yet dependable. Treat app-backed numbers as runtime-path evidence, not as a clean fresh-session benchmark until that bridge behavior is fixed.

## Fast Iteration

Use the smoke pack first when you are testing prompt changes or CLI compatibility:

```bash
bun run benchmark:latency benchmarks/latency/planning-latency-smoke.json \
  --json-out output/latency/planning-latency-smoke.jsonl
python3 ./scripts/latency_report.py output/latency/planning-latency-smoke.jsonl \
  --markdown-out output/latency/planning-latency-smoke.md
```

The JSONL file is written incrementally during the run, so you can inspect partial turn records without waiting for the whole pack to finish.

## Run The Harness

```bash
bun run benchmark:latency benchmarks/latency/planning-latency-core.json \
  --json-out output/latency/planning-latency-core.jsonl
python3 ./scripts/latency_report.py output/latency/planning-latency-core.jsonl \
  --markdown-out output/latency/planning-latency-core.md
```
