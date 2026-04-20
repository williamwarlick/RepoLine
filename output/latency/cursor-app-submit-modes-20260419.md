# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cursor-app-submit-modes-20260419.jsonl`
Generated: `2026-04-20 02:04 UTC`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider | Model | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| cursor | composer-2-fast | cursor-app-active-input | - | turn-1 | fresh | 0/2 | - | - | - | - | 20.03s | provider error observed |
| cursor | composer-2-fast | cursor-app-active-input | - | turn-2 | warm | 0/2 | - | - | - | - | 20.02s | provider error observed |
| cursor | composer-2-fast | cursor-app-bridge-handle | - | turn-1 | fresh | 0/2 | - | - | - | - | 0.13s | provider error observed |
| cursor | composer-2-fast | cursor-app-bridge-handle | - | turn-2 | warm | 0/2 | - | - | - | - | 0.09s | provider error observed |
| cursor | composer-2-fast | cursor-cli | - | turn-1 | fresh | 1/2 | 3.34s | 3.34s | 3.34s | 3.34s | 32.75s | timeout observed |
| cursor | composer-2-fast | cursor-cli | - | turn-2 | warm | 1/1 | 3.50s | 3.50s | 3.50s | 3.50s | 5.66s | - |
| cursor | composer-2-fast | cursor-cli | - | turn-2 | fresh | 1/1 | 4.72s | 4.72s | 4.66s | 4.66s | 7.04s | - |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
