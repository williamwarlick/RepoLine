# Testing And Quality Gates

Use `bin/check` from the repo root unless you need a narrower target.

## Standard Commands

```bash
bin/check quick
bin/check
```

`bin/check quick` is the normal handoff gate. It runs:

- root Bun tests for setup, doctor, installation contract, and runtime config scripts
- Python agent pytest
- frontend lint
- frontend typecheck
- frontend Bun tests

`bin/check` adds the frontend production build.

## Targeted Commands

```bash
bin/check scripts
bin/check agent
bin/check frontend
bin/check frontend-build
```

Use targeted commands while iterating, then run the smallest command that covers the touched surface before handing work back.

## Raw Commands

These are the underlying commands when a lower-level failure needs direct reproduction:

```bash
bun test scripts/*.test.ts
cd agent && uv run pytest
cd frontend && bun run lint
cd frontend && bun run typecheck
cd frontend && bun test
cd frontend && bun run build
```

Do not use bare `python`, `pytest`, `tsc`, or `next` when a repo command covers the same path.
