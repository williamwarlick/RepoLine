# Architecture

## Core decision

This bridge does not supply an LLM to LiveKit.

Instead:

- LiveKit handles room transport, STT, and TTS
- Claude Code remains the actual agent
- the bridge feeds final user transcripts into Claude Code
- the bridge forwards Claude Code partial text back into LiveKit TTS

## Why this shape

It matches the product goal more closely than a built-in LiveKit LLM:

- same coding agent you already use on desktop
- same Claude Code permissions and tool behavior
- no duplicated tool layer inside LiveKit
- partial spoken output as soon as Claude Code emits text deltas

## Data flow

1. Phone or browser joins the LiveKit room through `frontend/`.
2. LiveKit STT produces partial and final user transcripts.
3. The bridge ignores partials for generation, but uses them to interrupt current speech.
4. On a final transcript, the bridge starts a Claude Code CLI turn.
5. Claude Code emits `stream-json` events with partial message deltas.
6. The bridge chunks those deltas into speakable sentence-sized text.
7. LiveKit TTS speaks those chunks into the room as they arrive.

## State ownership

The bridge does not mirror or replay conversation history locally.

The only continuity it keeps is a room-scoped Claude session ID. Claude Code owns the real conversation state.

## Current non-goals

- phone number ingress
- Twilio or SIP trunking
- Codex support
- custom chat memory in the bridge
- local STT or local TTS in this repo
