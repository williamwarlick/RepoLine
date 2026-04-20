# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cursor-app-promotion-runtime-20260419.jsonl`
Generated: `2026-04-20 02:41 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| cursor | composer-2-fast | cursor-app-auto-investigation | light-investigation | experimental-path-1 | fresh | 2/2 | 3.05s | 3.22s | 3.05s | 3.22s | 3.10s | - |
| cursor | composer-2-fast | cursor-cli-investigation | light-investigation | experimental-path-1 | fresh | 2/2 | 3.22s | 3.33s | 3.22s | 3.33s | 4.62s | - |
| cursor | composer-2-fast | cursor-app-auto-summary | planning-question | repo-summary-1 | fresh | 2/2 | 2.70s | 3.02s | 2.70s | 3.02s | 2.76s | - |
| cursor | composer-2-fast | cursor-app-auto-warm-sequence | planning-question | repo-summary-1 | warm | 2/2 | 2.19s | 2.38s | 2.19s | 2.38s | 2.24s | - |
| cursor | composer-2-fast | cursor-app-auto-warm-sequence | planning-question | repo-summary-1 | fresh | 2/2 | 2.25s | 2.50s | 2.25s | 2.50s | 2.31s | - |
| cursor | composer-2-fast | cursor-app-auto-warm-sequence | planning-question | harness-path-1 | warm | 2/2 | 2.49s | 2.60s | 2.43s | 2.55s | 2.49s | - |
| cursor | composer-2-fast | cursor-cli-summary | planning-question | repo-summary-1 | fresh | 2/2 | 3.35s | 3.39s | 3.28s | 3.28s | 4.21s | - |
| cursor | composer-2-fast | cursor-cli-warm-sequence | planning-question | harness-path-1 | warm | 2/2 | 3.29s | 3.50s | 3.28s | 3.48s | 5.80s | - |
| cursor | composer-2-fast | cursor-cli-warm-sequence | planning-question | repo-summary-1 | warm | 2/2 | 4.54s | 5.35s | 4.50s | 5.28s | 5.40s | - |
| cursor | composer-2-fast | cursor-cli-warm-sequence | planning-question | repo-summary-1 | fresh | 2/2 | 4.65s | 5.36s | 4.56s | 5.23s | 5.10s | - |
| cursor | composer-2-fast | cursor-app-auto-lookup | repo-lookup | harness-path-1 | fresh | 2/2 | 3.50s | 4.63s | 3.48s | 4.62s | 3.53s | - |
| cursor | composer-2-fast | cursor-cli-lookup | repo-lookup | harness-path-1 | fresh | 2/2 | 4.08s | 4.32s | 4.06s | 4.28s | 6.87s | - |
| cursor | composer-2-fast | cursor-app-auto-hello | trivial-conversation | hello-1 | fresh | 2/2 | 2.59s | 2.96s | 2.59s | 2.96s | 2.65s | - |
| cursor | composer-2-fast | cursor-cli-hello | trivial-conversation | hello-1 | fresh | 2/2 | 5.12s | 6.76s | 5.07s | 6.71s | 5.64s | - |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
