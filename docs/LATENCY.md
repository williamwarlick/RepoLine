# Latency Notes

RepoLine phone latency is the sum of several stages:

1. Speech endpointing and transcript debounce.
2. Provider startup and session resume.
3. First model text delta.
4. Chunking into speakable text.
5. TTS playout start.

## What We Measured

On `2026-04-13`, a real Gemini CLI phone call in RepoLine showed:

- `0.35s` to `0.55s` is the target debounce window after the latest tuning.
- `gemini-2.5-flash` still spent about `5.8s` before `Gemini CLI started a session`.
- the first spoken chunk for `What is two plus two?` arrived about `7.4s` after model start before the debounce tuning, and the raw Gemini CLI first assistant delta landed in the same general range.

The important result is that the Gemini model itself was not the slow part.
Gemini CLI debug output reported API latency around `1.2s` to `1.6s`, while the full headless CLI wall time was much higher.

That means most of the latency is in the CLI wrapper path:

- auth and startup
- workspace and memory discovery
- session setup
- headless command orchestration

## Raw Gemini Findings

For the trivial prompt `What is two plus two? Reply with one short sentence.`:

- `gemini --output-format json` reported API latency around `1.5s`.
- `gemini --output-format stream-json` emitted:
  - `init` at about `6.1s`
  - first assistant delta (`"Two"`) at about `8.1s`
  - second assistant delta (`" plus two is four."`) at about `8.8s`

RepoLine was already reading Gemini as a stream.
The bridge was not waiting for the full final answer.
The main remaining tax was that Gemini CLI did not emit the first assistant delta until late.

## Direct Gemini API

RepoLine now also supports a direct Gemini Developer API transport.

On the same machine, through the RepoLine provider-stream path with:

- `BRIDGE_CLI_PROVIDER=gemini`
- `BRIDGE_GEMINI_TRANSPORT=api`
- `BRIDGE_MODEL=gemini-2.5-flash`
- `thinkingBudget=0` for `gemini-2.5` voice turns

the measured first spoken chunk was much faster:

- `What is two plus two?` -> about `689 ms`
- `What does RepoLine do?` -> about `637 ms`

That direct API path removes the Gemini CLI startup/orchestration tax and is the current best low-latency conversation mode for RepoLine.

## RepoLine-side Changes

RepoLine now uses faster voice timing defaults:

- `FINAL_TRANSCRIPT_DEBOUNCE_SECONDS=0.35`
- `BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS=0.55`
- `LIVEKIT_TURN_MIN_ENDPOINTING_DELAY_SECONDS=0.35`
- `LIVEKIT_TURN_MAX_ENDPOINTING_DELAY_SECONDS=1.4`

These changes reduce bridge overhead, but they do not remove the larger Gemini CLI startup cost.

## What Makes It Slower

- Personal OAuth in Gemini CLI headless mode.
- Large implicit CLI context and memory discovery.
- Headless session startup on every turn, even when the underlying model answer is simple.
- Waiting for a speakable sentence instead of a bare token.

## What Did Not Prove Out

- Adding a repo-local `.geminiignore` did not materially reduce Gemini CLI startup for this repo.
- `gemini-2.5-flash-lite` was not faster than `gemini-2.5-flash` in the local tests.

## Best Next Step

If you want phone conversations to feel truly immediate, prefer the direct Gemini API transport instead of the Gemini CLI wrapper:

- set `BRIDGE_GEMINI_TRANSPORT=api`
- provide `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- keep `gemini-2.5-flash` for the current latency/quality balance

The Gemini CLI path is still useful when you explicitly want its local tooling flow, but it is not the right default for fast back-and-forth voice conversation.
