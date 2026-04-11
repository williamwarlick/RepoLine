# Agent

This LiveKit agent does three things:

1. receives user speech from LiveKit STT
2. sends the final transcript to Claude Code
3. speaks Claude Code's partial output back through LiveKit TTS

## Commands

```bash
uv sync
uv run python src/agent.py download-files
uv run python src/agent.py dev
```

Use `console` instead of `dev` if you want to test the agent locally without the web frontend.

## Important env vars

- `LIVEKIT_AGENT_NAME`
- `CLAUDE_WORKDIR`
- `CLAUDE_MODEL`
- `CLAUDE_SYSTEM_PROMPT`
- `LIVEKIT_STT_MODEL`
- `LIVEKIT_TTS_MODEL`
