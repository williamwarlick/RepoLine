# RepoLine Latency Summary

Source: `/Users/wwarlick/development/agent-phone-bridge/output/latency/cross-provider-latency-v1.jsonl`
Generated: `2026-04-20 14:21 UTC`
Benchmark family: `cross_provider_latency`
Benchmark revision: `v1`
Run: `d5349f8869ab4b12993cdb24c3edbc27` at `2026-04-20T13:50:17Z`
Host: `Darwin` `arm64` on Python `3.13.11`
Git: `d77cf68`
Plan SHA-256: `acd12a571808`

This is a local diagnostic summary over normalized JSONL turn records.

| Provider path | Model | Transport | Submit mode | Fresh strategy | Prompt variant | Archetype | Prompt id | Session | ok/n | Median spoken | p90 spoken | Median assistant | p90 assistant | Median done | Warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 3/3 | 4.30s | 4.32s | 4.30s | 4.32s | 4.40s | - |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 3/3 | 5.37s | 5.58s | 5.36s | 5.56s | 6.74s | - |
| Codex CLI | default | - | - | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 3/3 | 7.71s | 8.22s | 7.71s | 8.22s | 8.01s | - |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | light-investigation | cursor-runtime-reason-1 | fresh | 0/3 | - | - | - | - | 6.32s | provider error observed |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | planning-question | repo-summary-1 | fresh | 6/6 | 4.12s | 4.22s | 4.12s | 4.22s | 4.19s | - |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | planning-question | repo-summary-1 | warm | 3/3 | 4.34s | 5.39s | 4.34s | 5.39s | 4.40s | - |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | planning-question | repo-summary-1 | warm | 3/3 | 4.51s | 4.80s | 4.51s | 4.79s | 5.48s | - |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | planning-question | repo-summary-1 | fresh | 6/6 | 4.52s | 5.71s | 4.32s | 5.64s | 6.02s | - |
| Codex CLI | default | - | - | - | current_baseline | planning-question | repo-summary-1 | fresh | 6/6 | 6.06s | 7.29s | 6.06s | 7.29s | 6.33s | - |
| Codex CLI | default | - | - | - | current_baseline | planning-question | repo-summary-1 | warm | 3/3 | 9.19s | 9.83s | 9.19s | 9.83s | 9.58s | - |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | planning-question | repo-summary-1 | fresh | 0/6 | - | - | - | - | 6.64s | provider error observed |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | planning-question | repo-summary-1 | warm | 0/3 | - | - | - | - | 6.47s | provider error observed |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 4.01s | 4.30s | 3.91s | 4.20s | 4.01s | - |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | repo-lookup | harness-path-1 | warm | 3/3 | 4.02s | 4.43s | 3.97s | 4.42s | 4.02s | - |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 4.87s | 5.43s | 4.87s | 5.43s | 5.93s | - |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | repo-lookup | harness-path-1 | warm | 3/3 | 5.81s | 7.58s | 5.81s | 7.58s | 7.73s | - |
| Codex CLI | default | - | - | - | current_baseline | repo-lookup | harness-path-1 | fresh | 3/3 | 8.46s | 9.08s | 8.46s | 9.08s | 17.11s | - |
| Codex CLI | default | - | - | - | current_baseline | repo-lookup | harness-path-1 | warm | 3/3 | 9.68s | 12.15s | 9.68s | 12.15s | 17.75s | - |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | repo-lookup | harness-path-1 | fresh | 0/3 | - | - | - | - | 6.26s | provider error observed |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | repo-lookup | harness-path-1 | warm | 0/3 | - | - | - | - | 7.25s | provider error observed |
| Cursor App (auto) | composer-2-fast | app | auto | - | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 4.07s | 4.13s | 4.07s | 4.13s | 4.16s | - |
| Cursor Agent CLI | composer-2-fast | cli | - | - | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 5.44s | 8.70s | 5.44s | 8.70s | 6.03s | - |
| Codex CLI | default | - | - | - | current_baseline | trivial-conversation | hello-1 | fresh | 3/3 | 6.27s | 6.57s | 6.27s | 6.57s | 6.54s | - |
| Gemini CLI | gemini-2.5-flash | cli | - | - | current_baseline | trivial-conversation | hello-1 | fresh | 2/3 | 29.01s | 40.32s | 15.70s | 16.36s | 14.96s | median spoken > 10s, p90 spoken > 30s, provider error observed |

## Notes

- `Median spoken` is the headline latency for the current scenario-runner harness.
- `Median assistant` is diagnostic only. It helps explain whether delay is before or after the first assistant delta.
- `Session` stays split between `fresh` and `warm`; do not average them together when making recommendations.

## Failure Reasons

### Gemini CLI

- `provider_error` x19: Gemini CLI failed with status error.
