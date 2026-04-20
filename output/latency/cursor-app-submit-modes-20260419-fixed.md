# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cursor-app-submit-modes-20260419-fixed.jsonl`
Generated: `2026-04-20 02:09 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| cursor | composer-2-fast | cursor-app-active-input | - | turn-2 | warm | 1/2 | 2.10s | 2.10s | 2.10s | 2.10s | 11.08s | provider error observed |
| cursor | composer-2-fast | cursor-app-active-input | - | turn-1 | fresh | 2/2 | 2.54s | 2.56s | 2.54s | 2.56s | 2.60s | - |
| cursor | composer-2-fast | cursor-app-bridge-handle | - | turn-1 | fresh | 0/2 | - | - | - | - | 0.25s | provider error observed |
| cursor | composer-2-fast | cursor-app-bridge-handle | - | turn-2 | warm | 0/2 | - | - | - | - | 0.20s | provider error observed |
| cursor | composer-2-fast | cursor-cli | - | turn-1 | fresh | 2/2 | 3.72s | 3.77s | 3.71s | 3.77s | 5.90s | - |
| cursor | composer-2-fast | cursor-cli | - | turn-2 | warm | 2/2 | 5.40s | 6.70s | 5.40s | 6.70s | 7.64s | - |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
