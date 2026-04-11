# Frontend

This is the LiveKit web client for the Claude Code phone bridge.

It does not talk to Claude Code directly. It only:

- gets a LiveKit token from `/api/token`
- joins a room
- explicitly dispatches to `AGENT_NAME=clawdbot-agent`
- provides the microphone and speaker UI

## Commands

```bash
bun install
bun run dev:network
```

Open the app from your laptop first. Then use your phone on the same network and browse to your laptop's LAN IP on port `3000`.
