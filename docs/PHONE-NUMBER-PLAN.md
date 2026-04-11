# Phone Number Plan

## Decision

Do not move Claude Code into LiveKit Cloud just to support an inbound phone number.

As of April 10, 2026, LiveKit's telephony docs describe inbound calls as SIP participants bridged into LiveKit rooms. A running named agent can be dispatched into those rooms. The docs explicitly show the agent being started normally and then receiving the call.

That means the current architecture can support a phone number:

- LiveKit Cloud manages the phone number, SIP ingress, and dispatch rules
- the local `clawdbot-agent` worker stays on the Mac
- Claude Code keeps local auth and access to the local Reflekta repo

## Recommended rollout

### Phase 1: Inbound number with local Claude bridge

Goal:

- make a LiveKit phone number ring into the existing `clawdbot-agent`

Steps:

1. Discover the active phone number already attached to the linked LiveKit project.
2. Create a SIP dispatch rule that routes each inbound call to a new room.
3. Scope that dispatch rule to the chosen project number.
4. Dispatch `clawdbot-agent` into that room explicitly.
5. Keep the local bridge running with `bun run dev`.
6. Add a phone-specific greeting and interruption tuning if needed.

Why this first:

- lowest risk
- keeps Claude local
- no cloud auth work for Claude Code
- no repo sync problem

## Dispatch rule

Use an individual room per call and explicit agent dispatch:

```json
{
  "dispatch_rule": {
    "name": "clawdbot-agent-inbound",
    "rule": {
      "dispatchRuleIndividual": {
        "roomPrefix": "call-",
        "pin": "1234"
      }
    },
    "roomConfig": {
      "agents": [
        {
          "agentName": "clawdbot-agent"
        }
      ]
    },
    "inboundNumbers": ["+15551234567"]
  }
}
```

## Setup flow

If the target LiveKit project already has one active number, the root setup wizard can discover it with `lk number list -j` and attach it automatically.

If the project has multiple active numbers, the wizard can ask which one to wire.

If the project has no number yet, add one in LiveKit first and rerun setup.

### 2. Create the dispatch rule

```bash
lk sip dispatch create -
```

The dispatch payload should scope inbound routing directly:

```json
{
  "dispatch_rule": {
    "name": "clawdbot-agent-inbound",
    "rule": {
      "dispatchRuleIndividual": {
        "roomPrefix": "call-",
        "pin": "1234"
      }
    },
    "roomConfig": {
      "agents": [
        {
          "agentName": "clawdbot-agent"
        }
      ]
    },
    "inboundNumbers": ["+15551234567"]
  }
}
```

### 4. Run the bridge locally

```bash
bun run dev
```

## Phase 2: Hybrid cloud media gateway

If the local worker is not good enough for telephony turn-taking, split responsibilities:

- LiveKit Cloud agent handles telephony ingress, turn detection, STT, TTS, and call lifecycle
- local bridge handles Claude Code and local repo access
- a narrow streaming protocol connects them

This is the right path if we want:

- better telephony reliability
- faster cloud-side interruption handling
- a future where the caller talks to a number even when the local web app is not open

## Phase 3: Full cloud execution

Only do this if Claude Code is no longer local-only for this project.

Requirements:

- non-interactive Claude auth in the cloud
- the Reflekta repo available in the cloud runtime
- a safe story for secrets and tool permissions

Without those, full cloud deployment breaks the main reason we are using Claude Code in the first place.
