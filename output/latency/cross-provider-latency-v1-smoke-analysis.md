# RepoLine Latency Analysis

- Benchmark family: `cross_provider_latency`
- Benchmark revision: `v1-smoke`
- Run id: `04fc6a41e2024e3695f985e84c813724`
- Run started: `2026-04-20T13:24:33Z`
- Git: `d77cf68`
- Host: `Darwin` `arm64` on Python `3.13.11`
- Plan path: `/Users/wwarlick/development/agent-phone-bridge/benchmarks/latency/cross-provider-latency-v1-smoke.json`
- Plan SHA-256: `5558e9eff70f`
- Generated: `2026-04-20 14:41 UTC`
- Rows: `24`

## Sources

- `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke.jsonl`

## Artifacts

- Provider comparison chart: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-provider-comparison.png`
- Fresh archetype chart: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-fresh-archetypes.png`
- Session delta chart: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-session-deltas.png`
- Provider summary CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-provider-summary.csv`
- Fresh archetype summary CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-fresh-archetypes.csv`
- Failure reasons CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-failure-reasons.csv`
- Session delta CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke-session-deltas.csv`

## Provider Success And Latency

| Session | Provider | ok/n | Success | Median spoken | p90 spoken | IQR spoken | 95% median CI | Median assistant | Median done |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh | Cursor App (auto) | 5/5 | 100% | 4.03s | 4.59s | 2.97s to 4.05s | 2.94s to 4.95s | 4.03s | 4.10s |
| fresh | Cursor Agent CLI | 5/5 | 100% | 4.52s | 7.38s | 4.29s to 6.29s | 4.18s to 8.12s | 4.51s | 7.05s |
| fresh | Codex CLI | 5/5 | 100% | 7.55s | 11.86s | 7.40s to 11.55s | 5.67s to 12.07s | 7.55s | 7.82s |
| fresh | Gemini CLI | 5/5 | 100% | 10.13s | 17.52s | 10.07s to 17.03s | 8.87s to 17.84s | 10.11s | 10.20s |
| warm | Cursor Agent CLI | 1/1 | 100% | 3.72s | 3.72s | 3.72s to 3.72s | 3.72s to 3.72s | 3.72s | 4.98s |
| warm | Cursor App (auto) | 1/1 | 100% | 4.02s | 4.02s | 4.02s to 4.02s | 4.02s to 4.02s | 4.02s | 4.09s |
| warm | Gemini CLI | 1/1 | 100% | 8.20s | 8.20s | 8.20s to 8.20s | 8.20s to 8.20s | 8.18s | 8.27s |
| warm | Codex CLI | 1/1 | 100% | 9.44s | 9.44s | 9.44s to 9.44s | 9.44s to 9.44s | 9.44s | 9.70s |

## Fresh Archetype Breakout

| Archetype | Provider | ok/n | Median spoken | IQR spoken | 95% median CI |
| --- | --- | ---: | ---: | ---: | ---: |
| Trivial Conversation | Cursor App (auto) | 1/1 | 4.95s | 4.95s to 4.95s | 4.95s to 4.95s |
| Trivial Conversation | Codex CLI | 1/1 | 7.55s | 7.55s to 7.55s | 7.55s to 7.55s |
| Trivial Conversation | Cursor Agent CLI | 1/1 | 8.12s | 8.12s to 8.12s | 8.12s to 8.12s |
| Trivial Conversation | Gemini CLI | 1/1 | 10.07s | 10.07s to 10.07s | 10.07s to 10.07s |
| Planning Question | Cursor App (auto) | 2/2 | 3.50s | 3.22s to 3.78s | 2.94s to 4.05s |
| Planning Question | Cursor Agent CLI | 2/2 | 4.23s | 4.20s to 4.26s | 4.18s to 4.29s |
| Planning Question | Codex CLI | 2/2 | 6.54s | 6.11s to 6.97s | 5.67s to 7.40s |
| Planning Question | Gemini CLI | 2/2 | 13.36s | 11.12s to 15.60s | 8.87s to 17.84s |
| Repo Lookup | Cursor App (auto) | 1/1 | 2.97s | 2.97s to 2.97s | 2.97s to 2.97s |
| Repo Lookup | Cursor Agent CLI | 1/1 | 4.52s | 4.52s to 4.52s | 4.52s to 4.52s |
| Repo Lookup | Gemini CLI | 1/1 | 10.13s | 10.13s to 10.13s | 10.13s to 10.13s |
| Repo Lookup | Codex CLI | 1/1 | 12.07s | 12.07s to 12.07s | 12.07s to 12.07s |
| Light Investigation | Cursor App (auto) | 1/1 | 4.03s | 4.03s to 4.03s | 4.03s to 4.03s |
| Light Investigation | Cursor Agent CLI | 1/1 | 6.29s | 6.29s to 6.29s | 6.29s to 6.29s |
| Light Investigation | Codex CLI | 1/1 | 11.55s | 11.55s to 11.55s | 11.55s to 11.55s |
| Light Investigation | Gemini CLI | 1/1 | 17.03s | 17.03s to 17.03s | 17.03s to 17.03s |

## Session Reuse Deltas

| Scope | Provider | Fresh ok/n | Warm ok/n | Fresh median spoken | Warm median spoken | Delta spoken | Delta % | Delta assistant | Delta done |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All Turns | Gemini CLI | 5/5 | 1/1 | 10.13s | 8.20s | -1.93s | -19% | -1.93s | -1.93s |
| All Turns | Cursor Agent CLI | 5/5 | 1/1 | 4.52s | 3.72s | -0.79s | -18% | -0.79s | -2.08s |
| All Turns | Cursor App (auto) | 5/5 | 1/1 | 4.03s | 4.02s | -0.01s | -0% | -0.01s | -0.01s |
| All Turns | Codex CLI | 5/5 | 1/1 | 7.55s | 9.44s | +1.89s | +25% | +1.89s | +1.88s |
| Planning Question | Gemini CLI | 2/2 | 1/1 | 13.36s | 8.20s | -5.16s | -39% | -5.17s | -5.16s |
| Planning Question | Cursor Agent CLI | 2/2 | 1/1 | 4.23s | 3.72s | -0.51s | -12% | -0.47s | -0.98s |
| Planning Question | Cursor App (auto) | 2/2 | 1/1 | 3.50s | 4.02s | +0.52s | +15% | +0.52s | +0.52s |
| Planning Question | Codex CLI | 2/2 | 1/1 | 6.54s | 9.44s | +2.90s | +44% | +2.90s | +2.89s |

## Notes

- This analysis rejects mixed benchmark families and revisions by default.
- It also rejects mixed plan hashes when plan fingerprints are present.
- Provider labels include transport and submit-mode qualifiers when those are part of the experiment contract.
- The provider comparison chart keeps `fresh` and `warm` separate on purpose.
- The archetype chart uses `fresh` turns only so it stays tied to one comparable prompt pack.
- Session delta rows report `warm - fresh`, so negative values mean a warm path is faster.
- The CSV artifacts are tidy exports for notebooks, slide decks, and downstream statistical work.

## Thin Sample Caveats

- `warm` `Cursor Agent CLI` has only `1` row(s); treat it as directional.
- `warm` `Cursor App (auto)` has only `1` row(s); treat it as directional.
- `warm` `Gemini CLI` has only `1` row(s); treat it as directional.
- `warm` `Codex CLI` has only `1` row(s); treat it as directional.
- `Trivial Conversation` / `Cursor App (auto)` has only `1` row(s).
- `Trivial Conversation` / `Codex CLI` has only `1` row(s).
- `Trivial Conversation` / `Cursor Agent CLI` has only `1` row(s).
- `Trivial Conversation` / `Gemini CLI` has only `1` row(s).
- `Planning Question` / `Cursor App (auto)` has only `2` row(s).
- `Planning Question` / `Cursor Agent CLI` has only `2` row(s).
- `Planning Question` / `Codex CLI` has only `2` row(s).
- `Planning Question` / `Gemini CLI` has only `2` row(s).
- `Repo Lookup` / `Cursor App (auto)` has only `1` row(s).
- `Repo Lookup` / `Cursor Agent CLI` has only `1` row(s).
- `Repo Lookup` / `Gemini CLI` has only `1` row(s).
- `Repo Lookup` / `Codex CLI` has only `1` row(s).
- `Light Investigation` / `Cursor App (auto)` has only `1` row(s).
- `Light Investigation` / `Cursor Agent CLI` has only `1` row(s).
- `Light Investigation` / `Codex CLI` has only `1` row(s).
- `Light Investigation` / `Gemini CLI` has only `1` row(s).
- `All Turns` / `Gemini CLI` has a thin session-delta sample (`fresh 5`, `warm 1`).
- `All Turns` / `Cursor Agent CLI` has a thin session-delta sample (`fresh 5`, `warm 1`).
- `All Turns` / `Cursor App (auto)` has a thin session-delta sample (`fresh 5`, `warm 1`).
- `All Turns` / `Codex CLI` has a thin session-delta sample (`fresh 5`, `warm 1`).
- `Planning Question` / `Gemini CLI` has a thin session-delta sample (`fresh 2`, `warm 1`).
- `Planning Question` / `Cursor Agent CLI` has a thin session-delta sample (`fresh 2`, `warm 1`).
- `Planning Question` / `Cursor App (auto)` has a thin session-delta sample (`fresh 2`, `warm 1`).
- `Planning Question` / `Codex CLI` has a thin session-delta sample (`fresh 2`, `warm 1`).
