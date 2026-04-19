# Benchmarking And Evals

RepoLine already has a latency harness. What was missing was a consistent way to compare models, transports, and variants without turning the results into a pile of screenshots and ad hoc notes.

This guide defines the benchmark shape to use going forward.

## What To Measure

Use multidimensional evaluation, not a single "fastest model wins" number.

- `success rate`: turns that exit cleanly and produce usable spoken text
- `eval pass rate`: turns that satisfy an objective check like exact match or required string includes
- `time to first spoken chunk`: the voice UX number that matters most in a phone or browser session
- `time to completed turn`: useful for total turn cost, but secondary to first spoken chunk
- `cold` versus `warm`: measure them separately, because resumed sessions often behave very differently from fresh turns

## Task Mix

Use at least two task families in every comparison suite:

- `voice UX tasks`: short natural prompts like `What does RepoLine do in one short sentence?`
- `objective lookup tasks`: prompts with exact or string-match expectations, like `Reply with just the path to the RepoLine Python latency harness wrapper script.`

That mix lets us see whether a variant is both fast and correct.

## Visualization Rules

Use charts to answer a narrow question, not to dump every metric into one figure.

- Make one latency chart per task
- Sort bars from fastest to slowest
- Keep `success rate` and `eval pass rate` in the table even if the chart focuses on latency
- Do not mix cold and warm runs in the same bar chart
- Keep labels short and stable with explicit `variant` metadata in the benchmark plan
- Always include sample size `n`

## Benchmark Plans

- [`benchmarks/latency/model-matrix-core.json`](../benchmarks/latency/model-matrix-core.json): portable provider and model comparison across the main CLI-backed variants
- [`benchmarks/latency/model-matrix-extended.json`](../benchmarks/latency/model-matrix-extended.json): optional app/API transport variants that depend on extra local setup
- [`benchmarks/latency/codex-conversation.json`](../benchmarks/latency/codex-conversation.json): warm-turn conversation benchmark

## Run The Core Matrix

```bash
bun run benchmark:latency benchmarks/latency/model-matrix-core.json \
  --json-out output/latency/model-matrix-core.json
python3 ./scripts/latency_report.py output/latency/model-matrix-core.json \
  --markdown-out output/latency/model-matrix-core.md
```

## Run The Extended Matrix

Use this only when the corresponding local transport is ready:

- Cursor app variants require a live Cursor desktop session on the target workspace
- Gemini API variants require `GEMINI_API_KEY` or `GOOGLE_API_KEY`

```bash
bun run benchmark:latency benchmarks/latency/model-matrix-extended.json \
  --json-out output/latency/model-matrix-extended.json
python3 ./scripts/latency_report.py output/latency/model-matrix-extended.json \
  --markdown-out output/latency/model-matrix-extended.md
```

## Interpretation

- Compare `success rate` first
- Compare `eval pass rate` second
- Compare `time to first spoken chunk` third
- Use `time to completed turn` as supporting context

If two variants are close on latency, prefer the one with higher pass rates and simpler operational requirements.
