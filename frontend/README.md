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

## Hosted Frontend

This frontend can also be deployed to Vercel as a private hosted deployment.

- enable Vercel deployment protection if your account supports it
- set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `AGENT_NAME`, and `NEXT_PUBLIC_APP_URL`
- set `REPOLINE_ACCESS_PIN` to require a PIN before loading the UI or issuing `/api/token`
- keep the LiveKit agent running somewhere else against the same LiveKit project

The browser entry point can move to Vercel, but the agent still needs repo and CLI access outside the frontend deployment in phase 1.
