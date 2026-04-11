---
name: repoline-tts-pronunciation
description: Tracks RepoLine pronunciation corrections for the active TTS provider. Use when a user says something sounded weird, was pronounced wrong, was spelled out letter by letter, or asks the agent to remember how a term should sound in future voice replies.
compatibility: Designed for skills-compatible coding agents running in RepoLine voice sessions over phone or browser via LiveKit.
---

# RepoLine TTS Pronunciation

Use this skill in RepoLine voice sessions when the user corrects how something should sound.

## What To Do

- Treat "you said that weird" as actionable speech feedback.
- Fix the wording immediately in the current reply when possible.
- Update [references/PROVIDER_NOTES.md](references/PROVIDER_NOTES.md) so the correction sticks for this TTS provider.
- Keep every rule short, explicit, and easy to apply while speaking.

## How To Write Rules

- Prefer direct patterns like `Say "README.md" as "read me."`
- Add what to avoid when needed, like `Do not spell out README.md letter by letter.`
- Keep the notes scoped to the provider listed in `PROVIDER_NOTES.md`.
- Preserve existing rules unless the user clearly wants to replace them.

## Confirmation Style

- Acknowledge the correction briefly.
- Mention that you updated the pronunciation notes if you changed them.
- Do not over-explain the TTS system unless the user asks.
