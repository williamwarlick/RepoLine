# Cursor App Validation: 2026-04-19

This note records the current Cursor App transport evidence used in RepoLine docs and recommendations.

## Runtime Result

Plan used: [`benchmarks/latency/cursor-app-promotion.json`](../benchmarks/latency/cursor-app-promotion.json)

Runtime-mode comparison on the tested Cursor desktop build:

- `Cursor App` transport with submit mode `auto`: `14/14` ok, median spoken `2494.9ms`, median done `2549.6ms`
- `Cursor Agent` CLI transport: `14/14` ok, median spoken `3536.8ms`, median done `4757.0ms`

Representative medians from that run:

- trivial hello: app `2.59s`, cli `5.12s`
- repo summary fresh: app `2.70s`, cli `3.35s`
- repo lookup fresh: app `3.50s`, cli `4.08s`
- warm-sequence repo summary: app `2.19s`, cli `4.54s`

Conclusion:

- `Cursor App` is the fastest current Cursor-backed runtime path in this repo
- `Cursor App` is stable enough for active runtime recommendation on the tested build
- `Cursor Agent` CLI remains the simpler fallback and the cleaner benchmark path

## Benchmark Caveat

Strict fresh-session benchmarking is not yet reliable on the tested Cursor desktop build.

What failed:

- `composer.createNew` succeeds
- the bridge appends a new id to `selectedComposerIds`
- the bridge does not reliably move `selectedComposerId` to that fresh composer

That means:

- app-backed runtime numbers are valid for the real selected-composer path
- they are not yet clean fresh-composer benchmark numbers
- use `Cursor Agent` CLI when you need simpler fresh-session isolation
