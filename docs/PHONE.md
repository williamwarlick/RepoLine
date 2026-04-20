# Phone Access

This project can attach a LiveKit phone number to the same local agent used for browser sessions.
Inbound calls arrive as SIP participants routed into LiveKit rooms through dispatch rules. That lets the phone path reuse the same local-worker architecture as the browser path instead of moving the coding CLI into LiveKit Cloud.

## Requirements

- a LiveKit Cloud project
- the `lk` CLI
- a local worker running with the same LiveKit credentials and agent name
- a coding CLI installed and authenticated on the machine that runs the worker

## Setup flow

1. Install `bun` first if it is missing.
2. Finish the local browser path first with `bun run setup --preset codex-browser`, `bun run doctor`, and `bun run live`.
3. Run `bun run setup:phone`. This reuses the existing RepoLine setup and only configures telephony.
4. If `lk` is not linked yet, setup can run `lk cloud auth` or let you add a project manually with API credentials.
5. Confirm the LiveKit project and agent name.
6. Let setup inspect the project's existing phone numbers.
7. If one number exists, setup can attach it automatically. If multiple numbers exist, choose the one to use.
8. If no active number exists yet, setup can search LiveKit for a US local number and purchase it from the CLI before continuing.
9. Pick the caller PIN, or pass one directly with `bun run setup:phone -- --pin 2468`.
10. Setup creates or updates the dispatch rule associated with the chosen number.

## Number provisioning note

Available numbers, regions, and charges depend on your LiveKit account and plan.
RepoLine can search and purchase a US local number from the CLI, but it does not hide LiveKit billing or regional availability constraints.

## Daily use

- Run `bun run live` when you want the local frontend and the worker together.
- Run `bun run agent` when the frontend is hosted somewhere else and only the worker needs to stay online.
- Call the configured number and enter the PIN when prompted.

## Operational limits

- The local worker has to be running for inbound calls to reach the CLI.
- CLI auth, secrets, and repo access stay on the machine that runs the worker.
- The default setup does not provide cloud-hosted CLI execution or automatic failover if the local worker goes offline.
