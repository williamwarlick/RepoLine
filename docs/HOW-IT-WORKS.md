# How It Works

This project is a voice bridge for a local coding CLI.

LiveKit handles media transport, speech-to-text, text-to-speech, and optional telephony. The coding CLI remains the real assistant, with its own tools, auth, and conversation state.

## Runtime model

1. A browser session or phone call joins a LiveKit room.
2. LiveKit converts speech into text.
3. Voice turns wait for a final transcript, while browser chat turns can be submitted immediately.
4. Provider output is broken into short spoken chunks when possible.
5. LiveKit speaks those chunks back into the room.
6. The browser UI can also show the message transcript and any RepoLine artifact cards the bridge publishes.

## What lives where

- LiveKit owns rooms, transport, STT, TTS, and phone ingress.
- The local agent owns turn coordination, interruption handling, and text chunking.
- The coding CLI owns reasoning, tool execution, filesystem access, and the actual conversation thread.

## Conversation state

The bridge does not maintain its own second copy of the full CLI conversation thread.

It does keep a few local runtime artifacts:

- the last completed provider session identifier in memory so the running worker can resume the next turn
- JSONL telemetry at `agent/logs/bridge-telemetry.jsonl` by default
- call summaries at `agent/logs/latest-call.md` and `agent/logs/calls/*.md`

The coding CLI remains the source of truth for the actual conversation thread. If you restart the worker, the in-memory resume session identifier is lost and the next turn starts fresh from the bridge side.

## Streaming behavior

Different CLIs expose different output surfaces:

- Claude Code currently has the best partial-text path, so speech can usually start before the turn fully completes.
- Codex resumes threads correctly, but local testing in this repo did not surface token deltas on stdout, so speech usually starts from the final assistant message.
- Cursor Agent can emit full assistant messages before the turn ends, but its stream is still coarser than Claude's delta stream.

## User-visible limits

- First response latency still depends on the CLI and any tool work it triggers.
- The local worker must be running for browser or phone sessions to reach the CLI.
- The bridge does not add a separate long-term memory layer.
- This repo does not ship a local STT or local TTS stack.
