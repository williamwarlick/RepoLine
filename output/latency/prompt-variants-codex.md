# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/prompt-variants-codex.jsonl`
Generated: `2026-04-19 22:20 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| codex | default | current_baseline | light-investigation | experimental-path-1 | fresh | 3/3 | 8.98s | 10.95s | - | - | 11.25s | - |
| codex | default | latency_minimal | light-investigation | experimental-path-1 | fresh | 3/3 | 8.19s | 9.00s | - | - | 12.58s | - |
| codex | default | planning_explicit | light-investigation | experimental-path-1 | fresh | 3/3 | 9.72s | 12.91s | - | - | 13.37s | - |
| codex | default | current_baseline | planning-question | repo-summary-1 | fresh | 3/3 | 5.04s | 9.79s | - | - | 5.32s | - |
| codex | default | latency_minimal | planning-question | repo-summary-1 | fresh | 3/3 | 5.63s | 8.14s | - | - | 5.92s | - |
| codex | default | planning_explicit | planning-question | repo-summary-1 | fresh | 3/3 | 5.07s | 5.41s | - | - | 5.35s | - |
| codex | default | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 6.20s | 8.26s | - | - | 14.91s | - |
| codex | default | latency_minimal | repo-lookup | harness-path-1 | fresh | 3/3 | 10.35s | 16.32s | - | - | 25.16s | median spoken > 10s |
| codex | default | planning_explicit | repo-lookup | harness-path-1 | fresh | 3/3 | 7.52s | 9.26s | - | - | 10.40s | - |
| codex | default | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 4.68s | 4.76s | - | - | 4.95s | - |
| codex | default | latency_minimal | trivial-conversation | hello-1 | fresh | 3/3 | 5.96s | 6.47s | - | - | 6.23s | - |
| codex | default | planning_explicit | trivial-conversation | hello-1 | fresh | 3/3 | 4.02s | 5.00s | - | - | 4.31s | - |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
