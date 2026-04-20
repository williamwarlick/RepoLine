# Benchmarking And Evals

RepoLine's current eval work is a local latency harness for coding agents. It is not a public scorecard product yet, and it is not trying to do rich answer-quality grading.

## Current Goal

Use the harness to answer practical questions:

- which coding-agent path starts speaking sooner
- whether the slowdown is before the first assistant delta or after it
- which prompt variant is faster for a given model
- how much warm-session reuse changes the result

## Canonical Output

The canonical artifact is one JSONL turn record per run.

Each record carries:

- `benchmark_family`
- `benchmark_revision`
- `plan_sha256`
- provider path, transport, and model
- `provider_submit_mode`
- `fresh_session_strategy`
- `prompt_variant`
- `latency_archetype`
- `prompt_id`
- `session_state`
- outcome classification
- explicit timing buckets

The timing buckets are:

- `provider_first_status_ms`
- `provider_first_assistant_delta_ms`
- `spoken_response_latency_ms`
- `completed_turn_ms`

Public language should use `spoken_response_latency_ms` as the headline latency. `provider_first_assistant_delta_ms` is diagnostic.

## Outcome States

The harness keeps a minimal floor so broken fast paths do not look good:

- `ok`
- `no_speech`
- `timed_out`
- `provider_error`
- `interrupted`

## Prompt And Task Dimensions

The harness now treats these as first-class:

- `prompt_variant`
  - `current_baseline`
  - `latency_minimal`
  - `planning_explicit`
- `latency_archetype`
  - `trivial-conversation`
  - `repo-lookup`
  - `planning-question`
  - `light-investigation`
- `session_state`
  - `fresh`
  - `warm`

Do not average `fresh` and `warm` together when making recommendations.

## Canonical Plans

- [`benchmarks/latency/cross-provider-latency-v1.json`](../benchmarks/latency/cross-provider-latency-v1.json): canonical current cross-provider pack across `codex`, `cursor app`, `cursor cli`, and `gemini cli`
- [`benchmarks/latency/cross-provider-latency-v1-smoke.json`](../benchmarks/latency/cross-provider-latency-v1-smoke.json): faster companion pack for checked-in artifacts and iteration with the same provider set
- [`benchmarks/latency/planning-latency-smoke.json`](../benchmarks/latency/planning-latency-smoke.json): fast smoke pack for day-to-day iteration
- [`benchmarks/latency/planning-latency-core.json`](../benchmarks/latency/planning-latency-core.json): legacy core comparison pack kept for continuity
- [`benchmarks/latency/prompt-variants-codex.json`](../benchmarks/latency/prompt-variants-codex.json): prompt-engineering pack for Codex

## Run The Canonical Cross-Provider Pack

```bash
bun run benchmark:latency benchmarks/latency/cross-provider-latency-v1.json \
  --json-out output/latency/cross-provider-latency-v1.jsonl
bun run benchmark:report output/latency/cross-provider-latency-v1.jsonl \
  --markdown-out output/latency/cross-provider-latency-v1.md
bun run benchmark:analyze output/latency/cross-provider-latency-v1.jsonl \
  --output-dir output/latency
```

`benchmark:analyze` writes:

- a provider comparison chart with separate `fresh` and `warm` panels
- a fresh-only archetype comparison chart
- a session-reuse delta chart showing `warm - fresh` median spoken latency by provider
- a Markdown summary with success rates, IQR, bootstrap median confidence intervals, and grouped failure reasons
- tidy CSV exports for provider summaries, fresh archetype summaries, session deltas, and failure reasons

For the current unified cross-provider packs, the Cursor App rows use the stable app transport path without forcing a fresh composer on every single-turn row. Strict fresh-composer isolation is still too version-sensitive to be part of the default comparison contract.

## Run The Smoke Pack

```bash
bun run benchmark:latency benchmarks/latency/planning-latency-smoke.json \
  --json-out output/latency/planning-latency-smoke.jsonl
bun run benchmark:report output/latency/planning-latency-smoke.jsonl \
  --markdown-out output/latency/planning-latency-smoke.md
```

## Run The Prompt-Variant Pack

```bash
bun run benchmark:latency benchmarks/latency/prompt-variants-codex.json \
  --json-out output/latency/prompt-variants-codex.jsonl
bun run benchmark:report output/latency/prompt-variants-codex.jsonl \
  --markdown-out output/latency/prompt-variants-codex.md
```

`--json-out` now writes incrementally during the run, so you can inspect partial JSONL records before a long pack finishes.

## Interpretation

- compare `ok` rate before comparing latency
- compare `median` and `p90`, not just average
- keep `benchmark_family`, `benchmark_revision`, and `plan_sha256` fixed when building charts
- use `spoken_response_latency_ms` for recommendation decisions
- use `provider_first_assistant_delta_ms` to understand where the time is going
- treat prompt-variant experiments as provider-specific unless the data shows they generalize
- treat groups with fewer than 3 rows as directional rather than stable
