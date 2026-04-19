# Onboarding And Defaults

Use this page for first-run setup decisions. It answers three questions:

1. What should a new user start with?
2. What does `bun run setup` actually write by default?
3. Which provider paths are recommended, merely supported, or still experimental?

Current guidance on this page reflects the repo state on April 19, 2026.

## Recommended First Run

For a new user, keep the first run boring:

- start with `Codex CLI`
- keep `BRIDGE_ACCESS_POLICY=readonly`
- run `bun run setup --provider codex --skip-phone` first if the goal is only to verify the browser flow
- run `bun run doctor` before wiring phone access
- add telephony only after the local browser path works

That path avoids the main onboarding traps:

- `Claude Code` is supported, but it has not been revalidated recently enough to make it the default recommendation
- `Cursor App` transport is experimental and version-sensitive
- `Gemini API` is fast, but it adds API-key setup that is not necessary for a clean first run

## What `bun run setup` Does

Setup:

- checks for `lk`, `uv`, `bun`, and the selected coding CLI
- offers install/bootstrap help for missing tools
- verifies provider authentication
- links or imports a LiveKit project
- writes `agent/.env.local`, `frontend/.env.local`, and `.bridge/state.json`
- installs the RepoLine voice skill and TTS pronunciation skill into the selected workdir
- installs agent and frontend dependencies
- optionally attaches or purchases a LiveKit phone number and creates dispatch wiring

If env files already exist, setup preserves existing overrides where possible and rewrites the generated files with the current project/provider/workdir values.

## Defaults Written By Setup

These are the baseline values written by `scripts/bridge-runtime-config.ts` unless you already have an override in `agent/.env.local` or `frontend/.env.local`.

### Agent defaults

| Setting | Default |
| --- | --- |
| `BRIDGE_CLI_PROVIDER` | the provider you choose in setup |
| `BRIDGE_MODEL` | empty for `claude` and `codex`; `composer-2-fast` for `cursor`; `gemini-2.5-flash` for `gemini` |
| `BRIDGE_CURSOR_TRANSPORT` | `cli` |
| `BRIDGE_GEMINI_TRANSPORT` | `cli` |
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

## Recommended Versus Supported

Use this table to decide what to put in front of a new user.

| Path | Onboarding status | Why |
| --- | --- | --- |
| `Codex CLI` | recommended default | lowest-ceremony first run in this repo; no extra transport flags; avoids Cursor App brittleness |
| `Gemini API` | recommended after baseline setup | best current voice-latency path when you are willing to manage `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| `Gemini CLI` | supported | works with the same setup flow, but voice latency is worse than the direct API path |
| `Cursor Agent` CLI transport | supported | reasonable if the user already lives in Cursor; use `cli` transport first |
| `Cursor App` transport | experimental | depends on an open Cursor desktop session, local bridge state, and current app compatibility |
| `Claude Code` | supported but not current default | keep support for existing Claude users, but rerun the core benchmark matrix before making it the recommended path again |

## Tested And Revalidation Guidance

The repo now has benchmark plans for all major provider families, but recommendation strength is not the same across them.

- Treat `Codex CLI` as the current onboarding baseline.
- Treat `Gemini API` as the current latency-focused upgrade path.
- Revalidate `Claude Code` before advertising it as the default recommendation again.
- Do not describe `Cursor App` as stable onboarding until it has a compatibility story that is less sensitive to the current Cursor desktop build.

If you want to refresh the recommendation table, rerun:

```bash
bun run benchmark:latency benchmarks/latency/model-matrix-core.json \
  --json-out output/latency/model-matrix-core.json
python3 ./scripts/latency_report.py output/latency/model-matrix-core.json \
  --markdown-out output/latency/model-matrix-core.md
```

Run the extended matrix only after the local transport is ready:

```bash
bun run benchmark:latency benchmarks/latency/model-matrix-extended.json \
  --json-out output/latency/model-matrix-extended.json
python3 ./scripts/latency_report.py output/latency/model-matrix-extended.json \
  --markdown-out output/latency/model-matrix-extended.md
```

## Recommended Onboarding Flow

1. Install `bun` and one coding CLI. For most new users, choose `codex`.
2. Run `bun run setup --provider codex --skip-phone`.
3. Run `bun run doctor`.
4. Run `bun run live` and verify the browser session on `http://127.0.0.1:3000`.
5. Re-run `bun run setup` without `--skip-phone` only after the local path is confirmed.
6. Move to `Gemini API` or `Cursor App` only as an explicit optimization pass, not as the initial install path.
