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

- provider path and model
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

- [`benchmarks/latency/planning-latency-core.json`](../benchmarks/latency/planning-latency-core.json): default coding-agent comparison pack
- [`benchmarks/latency/prompt-variants-codex.json`](../benchmarks/latency/prompt-variants-codex.json): prompt-engineering pack for Codex

## Run The Core Pack

```bash
bun run benchmark:latency benchmarks/latency/planning-latency-core.json \
  --json-out output/latency/planning-latency-core.jsonl
python3 ./scripts/latency_report.py output/latency/planning-latency-core.jsonl \
  --markdown-out output/latency/planning-latency-core.md
```

## Run The Prompt-Variant Pack

```bash
bun run benchmark:latency benchmarks/latency/prompt-variants-codex.json \
  --json-out output/latency/prompt-variants-codex.jsonl
python3 ./scripts/latency_report.py output/latency/prompt-variants-codex.jsonl \
  --markdown-out output/latency/prompt-variants-codex.md
```

## Interpretation

- compare `ok` rate before comparing latency
- compare `median` and `p90`, not just average
- use `spoken_response_latency_ms` for recommendation decisions
- use `provider_first_assistant_delta_ms` to understand where the time is going
- treat prompt-variant experiments as provider-specific unless the data shows they generalize
