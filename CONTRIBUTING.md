# Contributing

## Development flow

1. Install `bun` if it is missing.
2. Run `bun run setup` once to generate local env files, link LiveKit, and install dependencies.
   For scripted setup or smoke tests, pass `-- --provider <name> --project <name> --workdir <path> --agent-name <name> --skip-phone`.
3. Run `bun run doctor` to confirm the local CLI, `lk`, `uv`, and `bun` are available.
4. Use `bun run dev` for the combined frontend + agent development loop.

## Validation

Run these checks before opening a pull request:

```bash
bin/check
```

Use `bin/check quick` while iterating if the frontend production build is not relevant to the change.

## Notes

- Do not commit `.env.local`, logs, or local Claude tool state.
- Keep repo docs and UI copy concrete. Delete stale setup artifacts and generic AI filler instead of layering on more prose.
- The hosted frontend access gate is a shared-secret barrier, not a user auth system.
- Keep the coding CLI local. RepoLine is designed around local repo access and local CLI authentication.
