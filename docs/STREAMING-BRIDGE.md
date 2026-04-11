# Streaming Bridge

## Claude Code output surface

Claude Code exposes partial assistant text over JSONL when run with:

```bash
claude -p --verbose --output-format=stream-json --include-partial-messages
```

The bridge watches `content_block_delta` events and converts them into sentence-sized text chunks.

## Why this matters

Without this stream, the voice layer has to wait for Claude Code to finish the entire turn.

With it, LiveKit TTS can start speaking as soon as the first coherent chunk arrives.

## Current implementation

- `agent/src/claude_stream.py` owns the Claude CLI subprocess and chunking logic
- `agent/src/agent.py` feeds those chunks into `session.say(...)`
- `scripts/agent_stream_bridge.py` is the standalone debug harness

## Limits

- first-token latency still depends on Claude Code
- tool-heavy turns can still pause before the first spoken chunk
- this is streaming speech output, not a speech-native realtime model

## Local debug example

```bash
python3 scripts/agent_stream_bridge.py \
  --working-directory /Users/wwarlick \
  --system-prompt "Speak briefly and conversationally." \
  "Explain what you are doing."
```
