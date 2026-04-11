# Streaming Bridge

## Provider output surfaces

Claude Code exposes partial assistant text over JSONL when run with:

```bash
claude -p --verbose --output-format=stream-json --include-partial-messages
```

The bridge watches `content_block_delta` events and converts them into sentence-sized text chunks.

Codex CLI exposes JSONL lifecycle events with:

```bash
codex exec --json
codex exec resume <thread-id> --json
```

In local testing for this repo, that surface includes `thread.started`, `turn.started`, `item.completed`, and `turn.completed`. The final assistant text arrives as an `agent_message` item. The binary knows about delta event types, but they were not surfaced on stdout here.

Cursor Agent exposes NDJSON events with:

```bash
cursor-agent -p --output-format stream-json
cursor-agent -p --output-format stream-json --resume <chat-id>
```

The bridge watches `assistant` events plus the final `result` event. Cursor's print mode can emit complete assistant messages before the turn finishes, which is enough to start TTS, but it is still coarser than Claude's partial-message deltas.

## Why this matters

Without a streaming surface, the voice layer has to wait for the entire turn to finish.

With it, LiveKit TTS can start speaking as soon as the first coherent chunk arrives.

## Current implementation

- `agent/src/model_stream.py` owns the provider adapters and chunking logic
- `agent/src/agent.py` feeds those chunks into `session.say(...)`
- `agent/src/repoline_skill.py` resolves the RepoLine voice skill and runtime session hint
- `scripts/agent_stream_bridge.py` is the standalone debug harness

## Limits

- first-token latency still depends on the underlying CLI
- tool-heavy turns can still pause before the first spoken chunk
- this is streaming speech output, not a speech-native realtime model
- Codex currently resumes sessions correctly, but speech starts from its final `agent_message` because `codex exec --json` did not surface token deltas in local testing
- Cursor currently resumes chats correctly through `--resume`, but its headless stream is message-level rather than token-level in the docs we validated

## Local debug example

```bash
python3 scripts/agent_stream_bridge.py \
  --provider claude \
  --working-directory /path/to/your/repo \
  --system-prompt "Speak briefly and conversationally." \
  "Explain what you are doing."
```
