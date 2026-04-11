# Frontend

This is the LiveKit web client for RepoLine.

It does not talk to your coding CLI directly. It only:

- gets a LiveKit token from `/api/token`
- joins a room
- optionally dispatches to `AGENT_NAME`
- provides the microphone, speaker, and browser chat UI
- renders the LiveKit message transcript plus RepoLine artifact cards published by the bridge

## Commands

```bash
bun install
bun run dev:network
```

Open the app from your laptop first. Then use your phone on the same network and browse to your laptop's LAN IP on port `3000`.

## Hosted Frontend

This frontend can also be deployed to Vercel as a private hosted deployment.

- enable Vercel deployment protection if your account supports it
- set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `NEXT_PUBLIC_APP_URL`
- set `AGENT_NAME` only if you want explicit dispatch to one named agent; leave it blank to rely on automatic dispatch
- set `REPOLINE_ACCESS_PIN` to a long random access code before loading the UI or issuing `/api/token`
- optionally set `REPOLINE_BLOCKED_HOSTS` to the stable public alias so only Vercel-protected deployment URLs stay usable
- keep the LiveKit agent running somewhere else against the same LiveKit project

The browser entry point can move to Vercel, but the agent still needs repo and CLI access outside the frontend deployment.
