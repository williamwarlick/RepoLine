# Architecture

## Core decision

This bridge does not supply an LLM to LiveKit.

Instead:

- LiveKit handles room transport, STT, and TTS
- a local coding CLI remains the actual agent
- the bridge feeds final user transcripts into that CLI
- the bridge forwards streamed CLI text back into LiveKit TTS

## Why this shape

It matches the product goal more closely than a built-in LiveKit LLM:

- same coding agent you already use on desktop
- same provider permissions and tool behavior
- no duplicated tool layer inside LiveKit
- partial spoken output as soon as the provider emits usable text

## Data flow

1. Phone or browser joins the LiveKit room through `frontend/`.
2. LiveKit STT produces partial and final user transcripts.
3. The bridge ignores partials for generation, but uses them to interrupt current speech.
4. On a final transcript, the bridge starts a coding CLI turn.
5. The provider emits JSON events and, when available, text deltas.
6. The bridge chunks those deltas or the final message into speakable sentence-sized text.
7. LiveKit TTS speaks those chunks into the room as they arrive.

## State ownership

The bridge does not mirror or replay conversation history locally.

The only continuity it keeps is a room-scoped provider session or thread ID. The coding CLI owns the real conversation state.

Behavior guidance lives in the project-scoped `repoline-voice-session` Agent Skill. RepoLine also installs a mutable local `repoline-tts-pronunciation` companion skill so pronunciation corrections stay scoped to the configured TTS provider. RepoLine only adds a small session hint at runtime.

## Current non-goals

- phone number ingress
- Twilio or SIP trunking
- custom chat memory in the bridge
- local STT or local TTS in this repo
