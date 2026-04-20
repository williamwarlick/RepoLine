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

For Cursor-backed sessions, the browser control bar also surfaces runtime model state:

- `Cursor Agent` CLI sessions can change the active model live for subsequent turns
- `Cursor App` sessions can also switch between the supported Cursor runtime models live by updating Cursor's local composer state

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

Cursor has two distinct conversation stores in practice:

- headless `cursor-agent --resume` can reuse a session id on the CLI side
- the Cursor desktop app keeps its own local composer state in Cursor's SQLite storage

RepoLine's version-sensitive Cursor app transport reads and follows the desktop app composer state directly. A headless CLI resume does not write new bubbles back into that local app store.

## Streaming behavior

Different CLIs expose different output surfaces:

- Claude Code currently has the best partial-text path, so speech can usually start before the turn fully completes.
- Codex resumes threads correctly, but local testing in this repo did not surface token deltas on stdout, so speech usually starts from the final assistant message.
- Cursor Agent can emit full assistant messages before the turn ends, but its stream is still coarser than Claude's delta stream.
- Cursor App transport can be faster than headless Cursor because it uses the live desktop session, and on the current tested build it is the fastest Cursor-backed runtime path, but it depends on the app being open and focused on the target workspace.
- Gemini CLI emits simple streaming JSON deltas and tool events, which makes it easy to benchmark and compare against the other provider adapters.

## User-visible limits

- First response latency still depends on the CLI and any tool work it triggers.
- The local worker must be running for browser or phone sessions to reach the CLI.
- The bridge does not add a separate long-term memory layer.
- This repo does not ship a local STT or local TTS stack.
