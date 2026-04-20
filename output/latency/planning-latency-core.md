# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/planning-latency-core.jsonl`
Generated: `2026-04-19 22:42 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| codex | default | current_baseline | light-investigation | experimental-path-1 | fresh | 3/3 | 7.20s | 7.27s | - | - | 10.73s | - |
| codex | default | current_baseline | light-investigation | stale-path-1 | fresh | 3/3 | 9.14s | 10.45s | - | - | 12.71s | - |
| gemini | gemini-2.5-flash | current_baseline | light-investigation | stale-path-1 | fresh | 3/3 | 14.80s | 17.91s | - | - | 29.90s | median spoken > 10s |
| gemini | gemini-2.5-flash | current_baseline | light-investigation | experimental-path-1 | fresh | 3/3 | 15.12s | 16.02s | - | - | 16.29s | median spoken > 10s |
| cursor | composer-2-fast | current_baseline | light-investigation | experimental-path-1 | fresh | 0/3 | - | - | - | - | 1.52s | provider error observed |
| cursor | composer-2-fast | current_baseline | light-investigation | stale-path-1 | fresh | 0/3 | - | - | - | - | 1.54s | provider error observed |
| codex | default | current_baseline | planning-question | repo-summary-1 | fresh | 6/6 | 4.83s | 6.68s | - | - | 5.11s | - |
| codex | default | current_baseline | planning-question | repo-summary-1 | warm | 6/6 | 5.12s | 5.66s | - | - | 5.40s | - |
| codex | default | current_baseline | planning-question | onboarding-default-1 | fresh | 3/3 | 5.87s | 6.20s | - | - | 6.16s | - |
| gemini | gemini-2.5-flash | current_baseline | planning-question | repo-summary-1 | fresh | 6/6 | 8.75s | 11.35s | - | - | 8.80s | - |
| gemini | gemini-2.5-flash | current_baseline | planning-question | onboarding-default-1 | fresh | 3/3 | 9.03s | 13.69s | - | - | 9.17s | - |
| gemini | gemini-2.5-flash | current_baseline | planning-question | repo-summary-1 | warm | 6/6 | 10.96s | 13.44s | - | - | 11.03s | median spoken > 10s |
| cursor | composer-2-fast | current_baseline | planning-question | onboarding-default-1 | fresh | 0/3 | - | - | - | - | 1.52s | provider error observed |
| cursor | composer-2-fast | current_baseline | planning-question | repo-summary-1 | fresh | 0/12 | - | - | - | - | 1.52s | provider error observed |
| codex | default | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 7.57s | 7.85s | - | - | 12.91s | - |
| codex | default | current_baseline | repo-lookup | cursor-transport-var-1 | fresh | 3/3 | 8.32s | 9.11s | - | - | 11.74s | - |
| gemini | gemini-2.5-flash | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 8.43s | 13.40s | - | - | 14.72s | - |
| gemini | gemini-2.5-flash | current_baseline | repo-lookup | cursor-transport-var-1 | fresh | 3/3 | 15.64s | 16.28s | - | - | 41.91s | median spoken > 10s |
| cursor | composer-2-fast | current_baseline | repo-lookup | cursor-transport-var-1 | fresh | 0/3 | - | - | - | - | 1.55s | provider error observed |
| cursor | composer-2-fast | current_baseline | repo-lookup | harness-path-1 | fresh | 0/3 | - | - | - | - | 1.55s | provider error observed |
| codex | default | current_baseline | trivial-conversation | math-1 | fresh | 3/3 | 4.31s | 5.03s | - | - | 4.58s | - |
| codex | default | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 6.94s | 7.75s | - | - | 7.22s | - |
| gemini | gemini-2.5-flash | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 7.62s | 9.37s | - | - | 7.68s | - |
| gemini | gemini-2.5-flash | current_baseline | trivial-conversation | math-1 | fresh | 3/3 | 8.25s | 12.35s | - | - | 8.29s | - |
| cursor | composer-2-fast | current_baseline | trivial-conversation | hello-1 | fresh | 0/3 | - | - | - | - | 1.73s | provider error observed |
| cursor | composer-2-fast | current_baseline | trivial-conversation | math-1 | fresh | 0/3 | - | - | - | - | 1.51s | provider error observed |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
