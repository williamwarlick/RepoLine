<p align="center">
  <img src="./docs/assets/repoline-readme-banner.png" alt="RepoLine" width="100%" />
</p>

<p align="center">
  <strong>Call your codebase.</strong><br />
  Talk to your local coding CLI from your phone or browser over LiveKit.
</p>

<p align="center">
  <a href="https://github.com/williamwarlick/RepoLine/actions/workflows/ci.yml">
    <img src="https://github.com/williamwarlick/RepoLine/actions/workflows/ci.yml/badge.svg" alt="CI" />
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-0f172a.svg" alt="MIT License" />
  </a>
  <img src="https://img.shields.io/badge/runtime-bun%20%2B%20uv-0b1320.svg" alt="bun and uv" />
  <img src="https://img.shields.io/badge/voice-LiveKit-0b1320.svg" alt="LiveKit" />
</p>

RepoLine bridges a LiveKit phone or browser session to a coding CLI running in a local repo.
The model stays local to your machine, keeps its existing auth and tool access, and speaks results back over voice.

## Quick Start

Prerequisites:

- `claude`, `codex`, or `cursor-agent`, installed and authenticated
- `lk`, already linked to the LiveKit project you want to use
- `bun`
- `uv`

Run:

```bash
bun run setup
bun run live
bun run doctor
```

`bun run setup` writes the local env files, installs dependencies, installs the RepoLine voice skill into the target repo, and can wire phone access if your LiveKit project already has a number.

## Run Modes

- `bun run live`: normal local use, including real calls
- `bun run dev`: hot reload while working on RepoLine itself
- `bun run agent`: start only the LiveKit worker when the frontend is hosted elsewhere

## What RepoLine Does

- connects browser sessions or phone calls to a local coding CLI workdir
- supports `claude`, `codex`, and `cursor`
- speaks streamed output as soon as the provider gives usable text
- keeps repo access, auth, and tool execution on your machine

## Security

RepoLine is local-first by default.

- new setups default to `BRIDGE_ACCESS_POLICY=readonly`
- the frontend binds to `127.0.0.1` unless you explicitly opt into remote access
- the local worker still has to be running for voice sessions and phone calls to reach your repo

## Docs

- [Docs index](./docs/README.md)
- [How it works](./docs/HOW-IT-WORKS.md)
- [Phone access](./docs/PHONE.md)
- [Costs and limits](./docs/COSTS.md)

## License

MIT. See [LICENSE](./LICENSE).
