# RepoLine Latency Analysis

- Benchmark family: `cross_provider_latency`
- Benchmark revision: `v1`
- Run id: `d5349f8869ab4b12993cdb24c3edbc27`
- Run started: `2026-04-20T13:50:17Z`
- Git: `d77cf68`
- Host: `Darwin` `arm64` on Python `3.13.11`
- Plan path: `/Users/wwarlick/development/agent-phone-bridge/benchmarks/latency/cross-provider-latency-v1.json`
- Plan SHA-256: `acd12a571808`
- Generated: `2026-04-20 14:41 UTC`
- Rows: `84`

## Sources

- `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1.jsonl`

## Artifacts

- Provider comparison chart: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-provider-comparison.png`
- Fresh archetype chart: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-fresh-archetypes.png`
- Session delta chart: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-session-deltas.png`
- Provider summary CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-provider-summary.csv`
- Fresh archetype summary CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-fresh-archetypes.csv`
- Failure reasons CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-failure-reasons.csv`
- Session delta CSV: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-session-deltas.csv`

## Provider Success And Latency

| Session | Provider | ok/n | Success | Median spoken | p90 spoken | IQR spoken | 95% median CI | Median assistant | Median done |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh | Cursor App (auto) | 15/15 | 100% | 4.10s | 4.32s | 3.73s to 4.22s | 3.61s to 4.24s | 4.10s | 4.19s |
| fresh | Cursor Agent CLI | 15/15 | 100% | 4.91s | 6.11s | 4.32s to 5.51s | 4.27s to 5.44s | 4.91s | 6.03s |
| fresh | Codex CLI | 15/15 | 100% | 6.39s | 8.43s | 6.06s to 8.26s | 6.09s to 8.34s | 6.39s | 6.65s |
| fresh | Gemini CLI | 2/15 | 13% | 29.01s | 40.32s | 21.94s to 36.08s | 14.87s to 43.15s | 15.70s | 6.47s |
| warm | Cursor App (auto) | 6/6 | 100% | 4.18s | 5.09s | 3.96s to 4.49s | 3.64s to 5.09s | 4.16s | 4.21s |
| warm | Cursor Agent CLI | 6/6 | 100% | 4.69s | 6.92s | 4.42s to 5.57s | 4.11s to 6.92s | 4.69s | 6.57s |
| warm | Codex CLI | 6/6 | 100% | 9.44s | 11.38s | 8.92s to 9.91s | 7.30s to 11.38s | 9.44s | 10.57s |
| warm | Gemini CLI | 0/6 | 0% | - | - | - | - | - | 6.86s |

## Fresh Archetype Breakout

| Archetype | Provider | ok/n | Median spoken | IQR spoken | 95% median CI |
| --- | --- | ---: | ---: | ---: | ---: |
| Trivial Conversation | Cursor App (auto) | 3/3 | 4.07s | 3.84s to 4.11s | 3.61s to 4.14s |
| Trivial Conversation | Cursor Agent CLI | 3/3 | 5.44s | 4.71s to 7.48s | 3.97s to 9.51s |
| Trivial Conversation | Codex CLI | 3/3 | 6.27s | 6.21s to 6.46s | 6.14s to 6.65s |
| Trivial Conversation | Gemini CLI | 2/3 | 29.01s | 21.94s to 36.08s | 14.87s to 43.15s |
| Planning Question | Cursor App (auto) | 6/6 | 4.12s | 3.91s to 4.19s | 3.66s to 4.22s |
| Planning Question | Cursor Agent CLI | 6/6 | 4.52s | 4.30s to 4.91s | 3.98s to 5.71s |
| Planning Question | Codex CLI | 6/6 | 6.06s | 5.02s to 6.31s | 4.67s to 7.29s |
| Planning Question | Gemini CLI | 0/6 | - | - | - |
| Repo Lookup | Cursor App (auto) | 3/3 | 4.01s | 3.75s to 4.19s | 3.49s to 4.37s |
| Repo Lookup | Cursor Agent CLI | 3/3 | 4.87s | 4.50s to 5.22s | 4.12s to 5.57s |
| Repo Lookup | Codex CLI | 3/3 | 8.46s | 8.42s to 8.85s | 8.39s to 9.24s |
| Repo Lookup | Gemini CLI | 0/3 | - | - | - |
| Light Investigation | Cursor App (auto) | 3/3 | 4.30s | 2.84s to 4.31s | 1.38s to 4.33s |
| Light Investigation | Cursor Agent CLI | 3/3 | 5.37s | 5.14s to 5.50s | 4.91s to 5.63s |
| Light Investigation | Codex CLI | 3/3 | 7.71s | 6.25s to 8.03s | 4.80s to 8.34s |
| Light Investigation | Gemini CLI | 0/3 | - | - | - |

## Session Reuse Deltas

| Scope | Provider | Fresh ok/n | Warm ok/n | Fresh median spoken | Warm median spoken | Delta spoken | Delta % | Delta assistant | Delta done |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All Turns | Cursor Agent CLI | 15/15 | 6/6 | 4.91s | 4.69s | -0.22s | -4% | -0.23s | +0.53s |
| All Turns | Cursor App (auto) | 15/15 | 6/6 | 4.10s | 4.18s | +0.08s | +2% | +0.06s | +0.02s |
| All Turns | Codex CLI | 15/15 | 6/6 | 6.39s | 9.44s | +3.05s | +48% | +3.05s | +3.92s |
| All Turns | Gemini CLI | 2/15 | 0/6 | 29.01s | - | - | - | - | +0.38s |
| Planning Question | Cursor Agent CLI | 6/6 | 3/3 | 4.52s | 4.51s | -0.00s | -0% | +0.20s | -0.54s |
| Planning Question | Cursor App (auto) | 6/6 | 3/3 | 4.12s | 4.34s | +0.22s | +5% | +0.22s | +0.20s |
| Planning Question | Codex CLI | 6/6 | 3/3 | 6.06s | 9.19s | +3.13s | +52% | +3.13s | +3.25s |
| Planning Question | Gemini CLI | 0/6 | 0/3 | - | - | - | - | - | -0.16s |
| Repo Lookup | Cursor App (auto) | 3/3 | 3/3 | 4.01s | 4.02s | +0.02s | +0% | +0.07s | +0.02s |
| Repo Lookup | Cursor Agent CLI | 3/3 | 3/3 | 4.87s | 5.81s | +0.94s | +19% | +0.94s | +1.80s |
| Repo Lookup | Codex CLI | 3/3 | 3/3 | 8.46s | 9.68s | +1.23s | +15% | +1.23s | +0.64s |
| Repo Lookup | Gemini CLI | 0/3 | 0/3 | - | - | - | - | - | +0.99s |

## Notes

- This analysis rejects mixed benchmark families and revisions by default.
- It also rejects mixed plan hashes when plan fingerprints are present.
- Provider labels include transport and submit-mode qualifiers when those are part of the experiment contract.
- The provider comparison chart keeps `fresh` and `warm` separate on purpose.
- The archetype chart uses `fresh` turns only so it stays tied to one comparable prompt pack.
- Session delta rows report `warm - fresh`, so negative values mean a warm path is faster.
- The CSV artifacts are tidy exports for notebooks, slide decks, and downstream statistical work.

## Failure Reasons

### Gemini CLI

- `provider_error` x19: Gemini CLI failed with status error.
