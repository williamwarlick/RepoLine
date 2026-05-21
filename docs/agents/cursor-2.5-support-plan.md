# Cursor 2.5 Support Plan

Date: 2026-05-21

This is the implementation plan for making Composer 2.5 a first-class Cursor-backed RepoLine model. Treat this as a model promotion on the existing `cursor` provider path, not as a new provider or transport.

## Current Evidence

- Cursor's Composer 2.5 changelog says Composer 2.5 became available in Cursor on 2026-05-18 and has both standard and fast variants. The fast variant is described as the default.
- Cursor's CLI docs, resolved through Context7 on 2026-05-21, show that headless automation uses `cursor-agent -p`, supports `--output-format json|stream-json|text`, supports `--stream-partial-output`, and exposes `--model`, `--list-models`, `--mode`, `--trust`, `--workspace`, `--sandbox`, `-f`, and `--approve-mcps`.
- Local Cursor Agent on this machine reports CLI version `2026.05.20-2b5dd59`.
- `cursor-agent models` includes `composer-2.5` and `composer-2.5-fast`.
- A read-only headless smoke run succeeded:

```bash
cursor-agent -p --mode ask --model composer-2.5-fast \
  --output-format stream-json --stream-partial-output --trust \
  "Reply with exactly: repoline-cursor-25-ok"
```

Observed result:

- the stream initialized with model `Composer 2.5 Fast`
- the stream emitted `thinking` events before assistant text
- partial assistant text arrived in multiple fragments
- the final `result` was successful with `repoline-cursor-25-ok`

## Repo Surfaces

- Defaults: `scripts/bridge-runtime-config.ts`, `agent/src/bridge_config.py`, and `agent/src/provider_stream/common.py` still default Cursor to `composer-2-fast`.
- Runtime model switching: `agent/src/turn_coordinator.py` only offers `composer-2-fast` and `composer-2`.
- Cursor App model state: `agent/src/cursor_app_tap.py` only knows the local app config shape for `composer-2-fast` and `composer-2`.
- Frontend model picker: `frontend/components/agents-ui/agent-control-bar.tsx` reads runtime options from session state, so it should not need hard-coded model changes.
- Setup and doctor: setup writes the Cursor default model, while doctor checks `cursor-agent` presence but not model availability.
- Benchmarks and docs: `docs/ONBOARDING.md`, `docs/LATENCY.md`, `docs/EVALS.md`, and the latency plans still use `composer-2-fast` as the current Cursor model.

## Product Contract

- Default access policy remains `BRIDGE_ACCESS_POLICY=readonly`.
- For read-only Cursor CLI sessions, RepoLine should keep using `--mode ask` instead of claiming sandboxed write safety.
- `workspace-write` may use Cursor Agent force mode only after a scratch-repo mutation validation proves the requested file edit path works and does not bypass the RepoLine access-policy language.
- `owner` remains high risk and must not become a phone or hosted default.
- Cursor 2.5 sandbox network controls are useful upstream capability, but RepoLine should not claim support for configuring Cursor network allowlists until there is a repo-owned setup or doctor check for that state.

## Implementation Checklist

1. Promote the default Cursor model to `composer-2.5-fast`.
   - Update `DEFAULT_CURSOR_MODEL` in TypeScript and Python runtime config.
   - Update tests that assert generated env defaults, bridge config defaults, call greetings, and provider commands.

2. Add Composer 2.5 to runtime model switching.
   - Expand `CURSOR_RUNTIME_MODEL_OPTIONS` to include `composer-2.5-fast`, `composer-2.5`, `composer-2-fast`, and `composer-2`.
   - Keep the older Composer 2 entries as rollback choices unless validation shows they no longer work.
   - Update frontend session-state tests for the expanded option list and labels.

3. Extend Cursor App model config only after verifying the app state shape.
   - Inspect a real Cursor App composer after selecting Composer 2.5 Fast and Composer 2.5.
   - Add `build_cursor_model_config()` support for the verified shape.
   - Add fixture tests that prove the app runtime model updater writes the correct `modelConfig`.

4. Harden the Cursor CLI adapter against the observed Composer 2.5 stream shape.
   - Add a regression test with `thinking` events followed by fragmented assistant text and a final full result.
   - The expected behavior is no duplicated speech chunks and no spoken thinking text.

5. Add model availability diagnostics.
   - When `BRIDGE_CLI_PROVIDER=cursor`, `bun run doctor` should verify that `cursor-agent models` contains the configured `BRIDGE_MODEL`.
   - The failure should tell the user to run `cursor-agent update`, `cursor-agent login`, or choose an installed model.

6. Add a focused Cursor 2.5 validation pack.
   - Include `cursor` CLI rows for `composer-2.5-fast`, `composer-2.5`, and the old `composer-2-fast` rollback model.
   - Include Cursor App rows only after the app model config shape is verified.
   - Keep `fresh` and `warm` rows separate.

7. Refresh public docs only after validation passes.
   - Add `docs/CURSOR-2.5-VALIDATION-2026-05-21.md` or a newer dated validation note.
   - Update `docs/ONBOARDING.md` support dates and default model text.
   - Update `docs/LATENCY.md` only with benchmark-backed statements.

## Validation Contract

Do not claim `Cursor Agent` or `Cursor App` Composer 2.5 support in the public matrix until all applicable evidence is checked in:

```bash
cursor-agent --version
cursor-agent models
cursor-agent -p --mode ask --model composer-2.5-fast \
  --output-format stream-json --stream-partial-output --trust \
  "Reply with exactly: repoline-cursor-25-ok"
bin/check quick
bin/check
bun run benchmark:latency benchmarks/latency/cursor-2.5-validation.json \
  --json-out output/latency/cursor-2.5-validation-YYYYMMDD.jsonl
bun run benchmark:report output/latency/cursor-2.5-validation-YYYYMMDD.jsonl \
  --markdown-out output/latency/cursor-2.5-validation-YYYYMMDD.md
```

Minimum evidence for the CLI path:

- the configured default model appears in `cursor-agent models`
- a read-only headless smoke run succeeds with `composer-2.5-fast`
- provider adapter tests cover the current stream shape
- setup and bridge config tests prove new default materialization
- benchmark rows produce at least three successful turns for the promoted model before comparing latency

Additional evidence for the Cursor App path:

- a checked-in note names the tested Cursor desktop build
- model switching writes the verified Composer 2.5 app state shape
- an app transport smoke run succeeds with `BRIDGE_CURSOR_TRANSPORT=app`, submit mode `auto`, and `composer-2.5-fast`

## Source Links

- Cursor Composer 2.5 changelog: https://cursor.com/changelog/composer-2-5
- Cursor Composer 2.5 announcement: https://cursor.com/blog/composer-2-5
- Cursor 2.5 changelog: https://cursor.com/changelog/2-5
- Cursor CLI output format docs: https://cursor.com/docs/cli/reference/output-format
- Cursor CLI parameter docs: https://cursor.com/docs/cli/reference/parameters
- Cursor headless CLI docs: https://cursor.com/docs/cli/headless
