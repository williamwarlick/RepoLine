# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/planning-latency-smoke-postprompt.jsonl`
Generated: `2026-04-19 23:58 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| codex | default | current_baseline | planning-question | repo-summary-1 | fresh | 1/1 | 6.91s | 6.91s | 6.91s | 6.91s | 7.21s | - |
| cursor | composer-2-fast | current_baseline | planning-question | repo-summary-1 | fresh | 1/1 | 12.63s | 12.63s | 12.57s | 12.57s | 15.12s | median spoken > 10s |
| gemini | gemini-2.5-flash | current_baseline | planning-question | repo-summary-1 | fresh | 1/1 | 20.09s | 20.09s | 20.09s | 20.09s | 20.13s | median spoken > 10s |
| codex | default | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 8.09s | 8.09s | 8.09s | 8.09s | 12.33s | - |
| cursor | composer-2-fast | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 19.56s | 19.56s | 19.18s | 19.18s | 21.85s | median spoken > 10s |
| gemini | gemini-2.5-flash | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 22.05s | 22.05s | 22.05s | 22.05s | 22.11s | median spoken > 10s |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
