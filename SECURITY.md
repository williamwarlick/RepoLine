# Security Policy

## Reporting a vulnerability

Please do not open a public issue for vulnerabilities involving secrets, authentication, telephony abuse, or arbitrary code execution.

Use a GitHub private vulnerability report if available for this repository. If that is not available, contact the repository owner privately and include:

- a short description of the issue
- impact and prerequisites
- clear reproduction steps
- any suggested mitigation

## Operating assumptions

- RepoLine is designed for local execution against a repo and CLI session you already trust.
- The agent process keeps your repo access, local CLI auth, and tool permissions. Treat the machine running it as the trust boundary.
- New setups default to `BRIDGE_ACCESS_POLICY=readonly`. Keep that default for phone or remotely reachable usage unless you have a strong reason not to.

## Hosted frontend and token route

- `frontend/app/api/token/route.ts` issues short-lived LiveKit room tokens. It is not a full user-auth system.
- If you host the frontend, keep the deployment private and gate it with `REPOLINE_ACCESS_PIN` at minimum.
- `REPOLINE_BLOCKED_HOSTS` can reject known public deployment aliases outright so only your intended protected hostname stays usable.
- Do not expose the frontend publicly without an additional access layer that matches your threat model.

## Secrets and exposure

- Treat LiveKit API credentials, phone numbers, SIP dispatch rules, and any repo reachable by the agent as sensitive.
- Avoid `BRIDGE_ACCESS_POLICY=owner` for telephony or hosted access. It is the highest-risk mode and is intentionally blocked by default unless you opt in.
- If you make RepoLine reachable over the internet, you are responsible for network controls, deployment protection, and monitoring abuse.
