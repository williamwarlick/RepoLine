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
- `REPOLINE_SKILL_NAME`
- `REPOLINE_TTS_PRONUNCIATION_SKILL_NAME`
- `BRIDGE_MODEL`
- `BRIDGE_THINKING_LEVEL`
- `BRIDGE_ACCESS_POLICY` (`readonly`, `workspace-write`, or `owner`)
- `BRIDGE_SYSTEM_PROMPT` for explicit overrides
- `LIVEKIT_STT_MODEL`
- `LIVEKIT_TTS_MODEL`

RepoLine now expects a hard cutover to the `BRIDGE_*` env shape. The selected repo must have the RepoLine voice instructions installed for the configured CLI unless you explicitly set `BRIDGE_SYSTEM_PROMPT`.

Access policy guide:

- `readonly`: repo questions and inspection only
- `workspace-write`: project edits inside the provider's safer write mode
- `owner`: highest-permission local mode for the machine owner
