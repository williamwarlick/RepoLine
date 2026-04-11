# Costs and Limits

Verified against LiveKit pricing and documentation on April 11, 2026.

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
- Prometheus metrics: off until `BRIDGE_PROMETHEUS_PORT` is set

## Biggest cost lines

- Browser sessions: WebRTC minutes plus STT and TTS inference
- Phone sessions: inbound calling minutes plus the same shared STT and TTS inference pool
- Observability: only billed when you enable recordings or event collection

## Included quotas that matter most

| Resource | Build (`$0/mo`) | Ship (`$50/mo`) | Why it matters here |
| --- | --- | --- | --- |
| LiveKit Inference credits | `$2.50` | `$5.00` | Shared across STT and TTS |
| WebRTC minutes | `5,000` | `150,000`, then `$0.0005/min` | Browser sessions |
| US local phone numbers | `1 free number` | `1 free number`, then `$1/month` per extra | Optional telephony |
| US local inbound minutes | `50` | `100`, then `$0.01/min` | Usually the first phone-specific limit |
| Agent session recordings | `1,000 min` | `5,000 min`, then `$0.005/min` | Only relevant if recordings are enabled |
| Agent observability events | `100,000` | `500,000`, then `$0.00003/event` | Traces, logs, and transcripts |

Two Build-plan rules matter in practice:

- Build quotas are hard limits. When you hit them, usage fails instead of billing overages.
- Build quotas and concurrency limits are shared across all of your free LiveKit projects.

LiveKit also rounds time-based usage up to the next minute. A 10-second connection bills as 1 minute, and a 70-second connection bills as 2 minutes.

## Inference pricing for the repo defaults

LiveKit currently lists:

- `deepgram/nova-3` multilingual STT at `$0.0092/min` on Build and Ship
- `cartesia/sonic-3` TTS at `$50.00` per million characters on Build and Ship

That means browser usage is usually limited by inference credits well before WebRTC minutes. Phone usage often hits included inbound-minute quotas before it exhausts the shared inference credit pool.

## Concurrency and limit checks

LiveKit's current Build-plan limits most likely to affect this repo are:

- `5` active STT inference connections
- `5` active TTS inference connections
- `100` total participants across rooms

Those limits come from LiveKit's quotas and limits documentation, not from this repo.

## Sources

- [LiveKit pricing](https://livekit.com/pricing)
- [LiveKit inference pricing](https://livekit.com/pricing/inference)
- [LiveKit quotas and limits](https://docs.livekit.io/deploy/admin/quotas-and-limits/)
- [LiveKit billing](https://docs.livekit.io/deploy/admin/billing/)
- [LiveKit phone numbers](https://docs.livekit.io/telephony/start/phone-numbers/)
