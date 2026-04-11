# Agent

This LiveKit agent does three things:

1. receives user speech from LiveKit STT
2. sends the final transcript to the configured coding CLI
3. speaks streamed CLI output back through LiveKit TTS

## Commands

```bash
uv sync
uv run python src/agent.py download-files
uv run python src/agent.py dev
```

Use `console` instead of `dev` if you want to test the agent locally without the web frontend.

## Important env vars

- `LIVEKIT_AGENT_NAME`
- `BRIDGE_CLI_PROVIDER`
- `BRIDGE_WORKDIR`
- `BRIDGE_MODEL`
- `REPOLINE_SKILL_NAME`
- `BRIDGE_SYSTEM_PROMPT` for explicit overrides
- `LIVEKIT_STT_MODEL`
- `LIVEKIT_TTS_MODEL`
