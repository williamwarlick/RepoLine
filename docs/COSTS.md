# Costs and Limits

This page documents the cost drivers created by RepoLine's default architecture.
It does not try to freeze exact LiveKit pricing, because those numbers can change independently of the repo.

## What the default setup uses

The default local-worker setup uses:

- LiveKit WebRTC transport for browser sessions
- LiveKit Phone Numbers for optional inbound calling
- LiveKit Inference for speech-to-text and text-to-speech
- optional LiveKit observability when recordings, logs, traces, or transcripts are enabled
- a local coding CLI for the actual assistant turn

The default setup does **not** deploy the worker to LiveKit Cloud, and it does **not** use a LiveKit-hosted LLM by default. That distinction matters because LiveKit's `Agent session minutes` apply to agents deployed on LiveKit Cloud, not to the default local-worker path used by this repo.

## Defaults that affect spend

Current defaults in [agent/.env.example](../agent/.env.example) are:

- STT: `deepgram/nova-3`
- TTS: `cartesia/sonic-3`
- recordings, traces, logs, and transcripts: off by default
- local bridge telemetry: on by default in `agent/logs/bridge-telemetry.jsonl`
- Prometheus metrics: off until `BRIDGE_PROMETHEUS_PORT` is set

## Biggest cost lines

- Browser sessions: WebRTC minutes plus STT and TTS inference
- Phone sessions: inbound calling minutes plus the same shared STT and TTS inference pool
- Purchased phone numbers: optional but billable in many LiveKit plans
- LiveKit observability: only billed when you enable recordings or cloud event collection

## What this repo does not add to your LiveKit bill

- Local CLI execution itself. RepoLine runs the coding CLI on your machine.
- Local bridge telemetry files such as `agent/logs/bridge-telemetry.jsonl` and `agent/logs/latest-call.md`.
- Repo-local skill installs in the target repo.

## Practical limit notes

- Browser usage is usually constrained by your LiveKit transport and inference quotas, not by RepoLine.
- Phone usage adds telephony-specific limits and charges on top of the same STT/TTS pool used by browser sessions.
- If you enable LiveKit recordings, logs, traces, or transcripts, you should expect extra cloud usage beyond the default local-worker path.
- RepoLine does not smooth over LiveKit plan limits. If your account cannot create numbers, start inference, or join rooms, the bridge cannot proceed.

## Check current pricing and quotas

## Sources

- [LiveKit pricing](https://livekit.com/pricing)
- [LiveKit inference pricing](https://livekit.com/pricing/inference)
- [LiveKit quotas and limits](https://docs.livekit.io/deploy/admin/quotas-and-limits/)
- [LiveKit billing](https://docs.livekit.io/deploy/admin/billing/)
- [LiveKit phone numbers](https://docs.livekit.io/telephony/start/phone-numbers/)
