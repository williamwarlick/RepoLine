# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/planning-latency-core-no-gemini.jsonl`
Generated: `2026-04-19 22:26 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| codex | default | current_baseline | light-investigation | experimental-path-1 | fresh | 3/3 | 8.57s | 10.14s | - | - | 13.05s | - |
| codex | default | current_baseline | light-investigation | stale-path-1 | fresh | 3/3 | 9.22s | 9.60s | - | - | 12.38s | - |
| cursor | composer-2-fast | current_baseline | light-investigation | experimental-path-1 | fresh | 0/3 | - | - | - | - | 1.56s | provider error observed |
| cursor | composer-2-fast | current_baseline | light-investigation | stale-path-1 | fresh | 0/3 | - | - | - | - | 1.55s | provider error observed |
| codex | default | current_baseline | planning-question | onboarding-default-1 | fresh | 3/3 | 5.84s | 6.90s | - | - | 6.16s | - |
| codex | default | current_baseline | planning-question | repo-summary-1 | warm | 6/6 | 6.05s | 7.10s | - | - | 6.33s | - |
| codex | default | current_baseline | planning-question | repo-summary-1 | fresh | 6/6 | 6.12s | 6.96s | - | - | 6.38s | - |
| cursor | composer-2-fast | current_baseline | planning-question | onboarding-default-1 | fresh | 0/3 | - | - | - | - | 1.77s | provider error observed |
| cursor | composer-2-fast | current_baseline | planning-question | repo-summary-1 | fresh | 0/12 | - | - | - | - | 1.54s | provider error observed |
| codex | default | current_baseline | repo-lookup | cursor-transport-var-1 | fresh | 3/3 | 7.45s | 8.50s | - | - | 11.16s | - |
| codex | default | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 7.66s | 9.96s | - | - | 12.60s | - |
| cursor | composer-2-fast | current_baseline | repo-lookup | cursor-transport-var-1 | fresh | 0/3 | - | - | - | - | 1.54s | provider error observed |
| cursor | composer-2-fast | current_baseline | repo-lookup | harness-path-1 | fresh | 0/3 | - | - | - | - | 1.55s | provider error observed |
| codex | default | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 4.18s | 4.50s | - | - | 4.47s | - |
| codex | default | current_baseline | trivial-conversation | math-1 | fresh | 3/3 | 4.23s | 4.66s | - | - | 4.69s | - |
| cursor | composer-2-fast | current_baseline | trivial-conversation | hello-1 | fresh | 0/3 | - | - | - | - | 1.53s | provider error observed |
| cursor | composer-2-fast | current_baseline | trivial-conversation | math-1 | fresh | 0/3 | - | - | - | - | 1.53s | provider error observed |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
