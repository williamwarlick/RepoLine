# Phone Access

This project can attach a LiveKit phone number to the same local agent used for browser sessions.

As of April 11, 2026, LiveKit documents inbound phone calls as SIP participants routed into LiveKit rooms through dispatch rules. That lets the phone path reuse the existing local-worker architecture instead of moving the coding CLI into LiveKit Cloud.

## Requirements

- a LiveKit project with an active phone number
- the `lk` CLI linked to that project
- a local worker running with the same LiveKit credentials and agent name
- a coding CLI installed and authenticated on the machine that runs the worker

## Setup flow

1. Run `bun run setup`.
2. Choose the LiveKit project, coding CLI, and repo workdir.
3. Let setup inspect the project's existing phone numbers.
4. If one number exists, setup can attach it automatically. If multiple numbers exist, choose the one to use.
5. Pick the caller PIN.
6. Setup creates or updates the dispatch rule scoped to the chosen number.

## Daily use

- Run `bun run live` when you want the local frontend and the worker together.
- Run `bun run agent` when the frontend is hosted somewhere else and only the worker needs to stay online.
- Call the configured number and enter the PIN when prompted.

## Operational limits

- The local worker has to be running for inbound calls to reach the CLI.
- CLI auth, secrets, and repo access stay on the machine that runs the worker.
- The default setup does not provide cloud-hosted CLI execution or automatic failover if the local worker goes offline.
