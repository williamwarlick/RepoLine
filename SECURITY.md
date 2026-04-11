# Security Policy

## Reporting a vulnerability

Please do not open a public issue for vulnerabilities involving secrets, authentication, telephony abuse, or arbitrary code execution.

Use a GitHub private vulnerability report if available for this repository. If that is not available, contact the repository owner privately and include:

- a short description of the issue
- impact and prerequisites
- clear reproduction steps
- any suggested mitigation

## Security notes for deployers

- `frontend/app/api/token/route.ts` is development-only. It intentionally throws outside development because it has no user authentication layer.
- The bridge is designed for local Claude Code execution. Review tool permissions, repo access, and telephony exposure carefully before making it internet-facing.
- Treat LiveKit API credentials, phone routing rules, and Claude-accessible repos as sensitive.
