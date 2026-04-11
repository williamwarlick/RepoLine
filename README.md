# Claude Code Phone Bridge

Talk to Claude Code from your phone or browser using LiveKit.

This repo does not provide its own LLM. LiveKit handles audio transport, STT, and TTS. Claude Code stays the real agent. The bridge forwards each final user turn into Claude Code and speaks Claude's partial output as it streams back.

## Architecture

- `frontend/`: LiveKit web client for browser and phone access
- `agent/`: LiveKit agent that receives STT turns and streams Claude Code output into TTS
- `scripts/phone-bridge.ts`: Bun setup, dev, and doctor commands
- `scripts/agent_stream_bridge.py`: local debug tool for inspecting Claude Code's partial-output stream

The bridge intentionally does not store mirrored chat history. Claude Code owns conversation continuity through its own session.

During a slower turn, the bridge now does three things:

- speaks one short bridge-generated acknowledgement immediately after a turn starts
- relies on Claude Code to narrate what it is doing once Claude begins replying
- merges closely spaced final transcripts before sending them to Claude
- prompts Claude Code to announce tool work and delegate deeper background investigation when useful

## Quick Start

Prerequisites:

- `claude` installed and authenticated
- `lk` installed and already linked to the LiveKit project you want to use
- `uv`
- `bun`

Run the three root commands:

```bash
bun run setup
bun run dev
bun run doctor
```

## What `setup` does

The setup wizard:

1. reads the LiveKit projects already linked in your `lk` CLI config
2. lets you choose the target project
3. lets you choose the Claude Code repo/workdir from discovered local git repos
4. writes `agent/.env.local` and `frontend/.env.local`
5. installs agent and frontend dependencies
6. pre-downloads agent runtime files
7. optionally wires inbound telephony from the project's existing LiveKit number

If the selected LiveKit project has exactly one active phone number, setup uses it automatically. If it has multiple, setup asks which one to attach. If it has none, setup tells you and skips phone wiring until the project has a number.

When phone wiring is enabled, setup creates or updates a SIP dispatch rule, asks for a 4-digit caller PIN, and scopes inbound routing to the configured LiveKit project number.

For production-like previews or a deployed frontend, set `NEXT_PUBLIC_APP_URL` so Open Graph and social metadata resolve to the correct host instead of localhost.

## Runtime Shape

This repo is optimized for one path:

1. LiveKit web session or inbound phone call
2. Remote STT and remote TTS through LiveKit Inference
3. Claude Code CLI as the coding agent
4. Incremental spoken output from Claude Code partial-message events

`bun run dev` starts both the Python LiveKit agent and the Bun-run frontend. The frontend binds to `0.0.0.0` so you can open it from your phone on the same network.

## Test From Your Phone

Open the frontend from your laptop browser first. Then open the same app from your phone on the same network using your laptop's LAN IP, for example:

```text
http://192.168.1.20:3000
```

When the app connects, it should dispatch to `clawdbot-agent`, greet you, and route your voice turn into Claude Code.

## Debugging the Claude stream

You can inspect Claude Code's partial text stream directly:

```bash
python3 scripts/agent_stream_bridge.py \
  --working-directory /Users/wwarlick \
  "Tell me what files are in the current directory."
```

The script emits JSONL events, including sentence-sized `speech_chunk` items.

## Observability

The bridge now emits telemetry in three places:

- local JSONL turn logs at `agent/logs/bridge-telemetry.jsonl`
- worker logs with LiveKit metrics and state transitions
- LiveKit Cloud session recording for traces, logs, and transcripts

Current defaults in `agent/.env.local` are:

- `LIVEKIT_RECORD_TRACES=true`
- `LIVEKIT_RECORD_LOGS=true`
- `LIVEKIT_RECORD_TRANSCRIPT=true`
- `LIVEKIT_RECORD_AUDIO=true`
- `BRIDGE_PROMETHEUS_PORT=9465`

When the agent is running locally, Prometheus metrics are exposed at:

```text
http://127.0.0.1:9465/metrics
```

## Known Limits

- Claude Code is still turn-based. This bridge speaks partial text as soon as Claude emits it, but Claude still decides when the first text chunk appears.
- The backend currently launches Claude Code per user turn. Continuity stays with Claude through its session ID, not through local transcript replay.
- The frontend token route is still development-only and needs a real auth layer before any internet-facing deployment. See [frontend/app/api/token/route.ts](/Users/wwarlick/development/agent-phone-bridge/frontend/app/api/token/route.ts#L20).
- The local worker still has to be running for inbound phone calls to reach Claude Code.

## License

MIT. See [LICENSE](/Users/wwarlick/development/agent-phone-bridge/LICENSE).
