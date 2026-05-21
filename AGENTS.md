<INSTRUCTIONS>
# RepoLine Agent Contract

RepoLine is a local-first voice bridge from LiveKit browser or phone sessions into local coding CLIs. The coding CLI owns repo access, tools, auth, and reasoning; RepoLine owns setup, turn coordination, streaming, UI, telemetry, and eval artifacts.

## Essentials

- Use repo-root paths in notes and commands.
- Use `bun` for root TypeScript scripts and `frontend/`; use `uv` inside `agent/`.
- Prefer `bin/check quick` before handing back code changes. Use `bin/check` for full verification, including the Next production build.
- Do not commit `.env.local`, `.bridge/`, logs, caches, local CLI state, or generated benchmark scratch files unless William asks for a specific artifact.
- Keep `BRIDGE_ACCESS_POLICY=readonly` as the default for phone or hosted access. Treat `owner` as high risk.
- Product support claims require checked-in validation evidence and a tested date. Do not call a provider path validated just because code exists.
- Keep public onboarding paths limited to coding-agent paths with local repo access.
- For provider, latency, or support-matrix changes, update `CONTEXT.md` and `docs/EVALS.md` when the domain terms or evidence contract changes.

## Progressive Disclosure

- [Current goals](docs/agents/goals.md)
- [Repo map](docs/agents/repo-map.md)
- [Testing and quality gates](docs/agents/testing.md)
- [Docs index](docs/README.md)
- [Domain language](CONTEXT.md)
</INSTRUCTIONS>
