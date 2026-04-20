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
- `Cursor App` remains experimental because it is version-sensitive

For current `Cursor Agent` CLI builds in readonly mode, the harness uses Cursor's read-only `ask` mode instead of forcing `--sandbox enabled`, because that sandbox mode can be unavailable on some systems.

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
