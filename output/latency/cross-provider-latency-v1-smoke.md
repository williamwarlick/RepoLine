# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1-smoke.jsonl`
Generated: `2026-04-20 13:28 UTC`
Benchmark family: `cross_provider_latency`
Benchmark revision: `v1-smoke`
Run: `04fc6a41e2024e3695f985e84c813724` at `2026-04-20T13:24:33Z`
Host: `Darwin` `arm64` on Python `3.13.11`
Git: `d77cf68`
Plan SHA-256: `5558e9eff70f`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider path | Model | Transport | Submit mode | Fresh strategy | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 1/1 | 4.03s | 4.03s | 4.03s | 4.03s | 4.10s | thin sample |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 1/1 | 6.29s | 6.29s | 6.28s | 6.28s | 7.05s | thin sample |
| Codex CLI | default | - | - | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 1/1 | 11.55s | 11.55s | 11.55s | 11.55s | 11.82s | median spoken > 10s, thin sample |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 1/1 | 17.03s | 17.03s | 17.02s | 17.02s | 17.12s | median spoken > 10s, thin sample |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | planning-question | repo-summary-1 | fresh | 2/2 | 3.50s | 3.94s | 3.50s | 3.94s | 3.57s | thin sample |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | planning-question | repo-summary-1 | warm | 1/1 | 3.72s | 3.72s | 3.72s | 3.72s | 4.98s | thin sample |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | planning-question | repo-summary-1 | warm | 1/1 | 4.02s | 4.02s | 4.02s | 4.02s | 4.09s | thin sample |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | planning-question | repo-summary-1 | fresh | 2/2 | 4.23s | 4.28s | 4.19s | 4.21s | 5.96s | thin sample |
| Codex CLI | default | - | - | - | current_baseline | planning-question | repo-summary-1 | fresh | 2/2 | 6.54s | 7.23s | 6.54s | 7.23s | 6.81s | thin sample |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | planning-question | repo-summary-1 | warm | 1/1 | 8.20s | 8.20s | 8.18s | 8.18s | 8.27s | thin sample |
| Codex CLI | default | - | - | - | current_baseline | planning-question | repo-summary-1 | warm | 1/1 | 9.44s | 9.44s | 9.44s | 9.44s | 9.70s | thin sample |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | planning-question | repo-summary-1 | fresh | 2/2 | 13.36s | 16.95s | 13.35s | 16.94s | 13.43s | median spoken > 10s, thin sample |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 2.97s | 2.97s | 2.89s | 2.89s | 2.97s | thin sample |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 4.52s | 4.52s | 4.51s | 4.51s | 7.24s | thin sample |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 10.13s | 10.13s | 10.11s | 10.11s | 10.18s | median spoken > 10s, thin sample |
| Codex CLI | default | - | - | - | current_baseline | repo-lookup | harness-path-1 | fresh | 1/1 | 12.07s | 12.07s | 12.07s | 12.07s | 18.95s | median spoken > 10s, thin sample |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | trivial-conversation | hello-1 | fresh | 1/1 | 4.95s | 4.95s | 4.95s | 4.95s | 5.03s | thin sample |
| Codex CLI | default | - | - | - | current_baseline | trivial-conversation | hello-1 | fresh | 1/1 | 7.55s | 7.55s | 7.55s | 7.55s | 7.82s | thin sample |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | trivial-conversation | hello-1 | fresh | 1/1 | 8.12s | 8.12s | 8.12s | 8.12s | 8.48s | thin sample |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | trivial-conversation | hello-1 | fresh | 1/1 | 10.07s | 10.07s | 10.07s | 10.07s | 10.20s | median spoken > 10s, thin sample |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.
