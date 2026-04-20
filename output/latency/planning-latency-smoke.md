# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/planning-latency-smoke.jsonl`
Generated: `2026-04-19 23:52 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| codex | default | current_baseline | planning-question | repo-summary-1 | fresh | 1/1 | 10.48s | 10.48s | 10.48s | 10.48s | 10.76s | median spoken > 10s |
| cursor | composer-2-fast | current_baseline | planning-question | repo-summary-1 | fresh | 1/1 | 11.37s | 11.37s | 11.36s | 11.36s | 13.67s | median spoken > 10s |
| gemini | gemini-2.5-flash | current_baseline | planning-question | repo-summary-1 | fresh | 1/1 | 18.38s | 18.38s | 18.38s | 18.38s | 18.43s | median spoken > 10s |
| codex | default | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 11.33s | 11.33s | 11.33s | 11.33s | 14.81s | median spoken > 10s |
| gemini | gemini-2.5-flash | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 12.11s | 12.11s | 12.11s | 12.11s | 12.14s | median spoken > 10s |
| cursor | composer-2-fast | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 18.26s | 18.26s | 18.02s | 18.02s | 20.55s | median spoken > 10s |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
