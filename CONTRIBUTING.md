# Contributing

## Development flow

1. Run `bun run setup` once to generate local env files and install dependencies.
2. Run `bun run doctor` to confirm `claude`, `lk`, `uv`, and `bun` are available.
3. Use `bun run dev` for the combined frontend + agent development loop.

## Validation

Run these checks before opening a pull request:

```bash
cd agent && uv run pytest
cd frontend && bun run lint
cd frontend && bun run typecheck
cd frontend && bun run build
```

## Notes

- Do not commit `.env.local`, logs, or local Claude tool state.
- The frontend token route is intentionally development-only and must not be used as a production auth model.
- Keep Claude Code local. This project is designed around local repo access and local Claude authentication.
