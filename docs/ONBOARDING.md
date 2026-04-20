# Onboarding And Defaults

Use this page for first-run setup decisions and the public support matrix.

Current guidance on this page reflects the repo state on April 19, 2026.

## Recommended First Run

For a new user, keep the first run boring:

- start with `Codex CLI`
- keep `BRIDGE_ACCESS_POLICY=readonly`
- run `bun run setup --preset codex-browser` first if the goal is only to verify the browser flow
- run `bun run doctor` before wiring phone access
- add telephony only after the local browser path works

That path avoids the main onboarding traps:

- `Claude Code` is currently stale support, not a default recommendation
- `Cursor App` is the fastest current Cursor-backed runtime path, but it is still version-sensitive and not the boring first-run default
- `Gemini CLI` is supported, but not the baseline path we want new users to start with

## What `bun run setup` Writes

These are the baseline generated defaults unless an existing env file already overrides them.

### Agent defaults

| Setting | Default |
| --- | --- |
| `BRIDGE_CLI_PROVIDER` | the provider you choose in setup |
| `BRIDGE_MODEL` | empty for `claude` and `codex`; `composer-2-fast` for `cursor`; `gemini-2.5-flash` for `gemini` |
| `BRIDGE_CURSOR_TRANSPORT` | `cli` |
| `BRIDGE_THINKING_LEVEL` | `low` |
| `BRIDGE_ACCESS_POLICY` | `readonly` |
| `REPOLINE_SKILL_NAME` | `repoline-voice-session` |
| `REPOLINE_TTS_PRONUNCIATION_SKILL_NAME` | `repoline-tts-pronunciation` |
| `BRIDGE_CHUNK_CHARS` | `80` |
| `BRIDGE_THINKING_SOUND_PRESET` | `soft-pulse` |
| `BRIDGE_THINKING_SOUND_INTERVAL_MS` | `1800` |
| `BRIDGE_THINKING_SOUND_VOLUME` | `0.11` |
| `BRIDGE_THINKING_SOUND_SIP_ONLY` | `true` |
| `FINAL_TRANSCRIPT_DEBOUNCE_SECONDS` | `0.35` |
| `BRIDGE_SHORT_TRANSCRIPT_WORDS` | `2` |
| `BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS` | `0.55` |
| `BRIDGE_STT_PROVIDER` | `livekit`, unless `DEEPGRAM_API_KEY` is already present |
| `LIVEKIT_STT_MODEL` | `deepgram/nova-3` |
| `BRIDGE_TTS_PROVIDER` | `livekit`, unless `ELEVENLABS_API_KEY` is already present |
| `LIVEKIT_TTS_MODEL` | `cartesia/sonic-3` |
| `LIVEKIT_RECORD_AUDIO` | `false` |
| `LIVEKIT_RECORD_TRACES` | `false` |
| `LIVEKIT_RECORD_LOGS` | `false` |
| `LIVEKIT_RECORD_TRANSCRIPT` | `false` |

### Frontend defaults

| Setting | Default |
| --- | --- |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` |
| `AGENT_NAME` | the agent name chosen in setup |
| frontend bind host at runtime | `127.0.0.1` unless you explicitly opt into remote access |

## Support Matrix

`Supported` here means recently validated with checked-in evidence and a tested date. Code presence alone is not enough.

| Path | Public status | Last validated | Evidence | Notes |
| --- | --- | --- | --- | --- |
| `Codex CLI` | validated support, recommended default | `2026-04-19` | targeted Python and Bun setup/runtime tests; default harness pack at [`benchmarks/latency/planning-latency-core.json`](../benchmarks/latency/planning-latency-core.json) | best current onboarding path |
| `Cursor Agent` CLI transport | validated support | `2026-04-19` | targeted Python and Bun setup/runtime tests; default harness pack at [`benchmarks/latency/planning-latency-core.json`](../benchmarks/latency/planning-latency-core.json) | supported, but not the default onboarding recommendation |
| `Gemini CLI` | validated support | `2026-04-19` | targeted Python and Bun setup/runtime tests; default harness pack at [`benchmarks/latency/planning-latency-core.json`](../benchmarks/latency/planning-latency-core.json) | supported coding-agent path with local repo access |
| `Cursor App` transport | validated runtime support | `2026-04-19` | targeted setup/runtime tests; checked-in validation note at [`docs/CURSOR-APP-VALIDATION-2026-04-19.md`](./CURSOR-APP-VALIDATION-2026-04-19.md) | fastest current Cursor-backed runtime path with `BRIDGE_CURSOR_TRANSPORT=app` and submit mode `auto`; still version-sensitive, but RepoLine can now switch the supported runtime models from the browser control bar |
| `Claude Code` | stale support | `2026-04-15` | older checked-in benchmark work; no fresh validation in the current cut | keep visible in the matrix, but do not treat it as currently validated |

## Recommended Onboarding Flow

1. Install `bun` and one coding CLI. For most new users, choose `codex`.
2. Run `bun run setup --preset codex-browser`.
3. Run `bun run doctor`.
4. Run `bun run live` and verify the browser session on `http://127.0.0.1:3000`.
5. Run `bun run setup:phone` only after the local path is confirmed and you want telephony.
6. Move to `Cursor App` only after the baseline install works if you want the fastest current Cursor-backed runtime path.
7. Use the browser control bar to change models live for `Cursor Agent` CLI and `Cursor App` sessions.
8. Keep `Cursor Agent` CLI as the simpler fallback when the app path is unstable or when you need a cleaner fresh-session benchmark path.

## Quick Phone Follow-Up

Once the browser path works, use the fast follow-up path instead of rerunning full setup:

```bash
bun run setup:phone
```

That reuses the existing provider, workdir, project, and agent name, then only attaches or updates the LiveKit phone number and dispatch rule. If you want a specific inbound PIN without prompting, use:

```bash
bun run setup:phone -- --pin 2468
```
