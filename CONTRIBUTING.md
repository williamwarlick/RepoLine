# Contributing

## Development flow

1. Run `./scripts/bootstrap.sh` on a fresh machine to install `bun`, `uv`, `lk`, and a supported coding CLI when needed.
2. Run `bun run setup` once to generate local env files, link LiveKit, and install dependencies.
3. Run `bun run doctor` to confirm the local CLI, `lk`, `uv`, and `bun` are available.
4. Use `bun run dev` for the combined frontend + agent development loop.

## Validation

Run these checks before opening a pull request:

```bash
bun test scripts/bridge-doctor.test.ts scripts/bridge-runtime-config.test.ts
cd agent && uv run pytest
cd frontend && bun run lint
cd frontend && bun run typecheck
cd frontend && bun test
cd frontend && bun run build
```

## Notes

- Do not commit `.env.local`, logs, or local Claude tool state.
- Keep repo docs and UI copy concrete. Delete stale setup artifacts and generic AI filler instead of layering on more prose.
- `.mise.toml` exists only to pin Bun for environments that already resolve `bun` through `mise`; bootstrap and CI do not require you to use `mise` directly.
- The hosted frontend access gate is a shared-secret barrier, not a user auth system.
- Keep the coding CLI local. RepoLine is designed around local repo access and local CLI authentication.
