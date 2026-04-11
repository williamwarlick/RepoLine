#!/usr/bin/env bash

set -euo pipefail

HOME_BIN_DIRS=(
  "$HOME/.bun/bin"
  "$HOME/.local/bin"
  "/opt/homebrew/bin"
  "/usr/local/bin"
)

for dir in "${HOME_BIN_DIRS[@]}"; do
  if [[ -d "$dir" && ":$PATH:" != *":$dir:"* ]]; then
    PATH="$dir:$PATH"
  fi
done

log() {
  printf '[bootstrap] %s\n' "$1"
}

fail() {
  printf '[bootstrap] %s\n' "$1" >&2
  exit 1
}

has() {
  command -v "$1" >/dev/null 2>&1
}

ensure_curl() {
  if ! has curl; then
    fail 'curl is required for bootstrap. Install curl first, then rerun this script.'
  fi
}

install_bun() {
  if has bun; then
    log 'bun already installed'
    return
  fi
  ensure_curl
  log 'installing bun via bun.sh'
  curl -fsSL https://bun.sh/install | bash
}

install_uv() {
  if has uv; then
    log 'uv already installed'
    return
  fi
  if has brew; then
    log 'installing uv via Homebrew'
    brew install uv
    return
  fi
  ensure_curl
  log 'installing uv via astral.sh'
  curl -LsSf https://astral.sh/uv/install.sh | sh
}

install_lk() {
  if has lk; then
    log 'lk already installed'
    return
  fi
  if has brew; then
    log 'installing LiveKit CLI via Homebrew'
    brew install livekit
    return
  fi
  fail 'lk is missing. Install Homebrew and rerun `./scripts/bootstrap.sh lk`, or install the LiveKit CLI manually.'
}

install_node() {
  if has npm; then
    return
  fi
  if has brew; then
    log 'installing Node.js via Homebrew'
    brew install node
    return
  fi
  fail 'npm is required to install this CLI. Install Node.js first, then rerun bootstrap.'
}

install_claude() {
  if has claude; then
    log 'claude already installed'
    return
  fi
  install_node
  log 'installing Claude Code via npm'
  npm install -g @anthropic-ai/claude-code
}

install_codex() {
  if has codex; then
    log 'codex already installed'
    return
  fi
  if [[ "$(uname -s)" == "Darwin" ]] && has brew; then
    log 'installing Codex CLI via Homebrew'
    brew install --cask codex
    return
  fi
  if has npm; then
    log 'installing Codex CLI via npm'
    npm install -g @openai/codex
    return
  fi
  fail 'codex is missing. Install Homebrew or npm first, then rerun `./scripts/bootstrap.sh codex`.'
}

install_cursor() {
  if has cursor-agent; then
    log 'cursor-agent already installed'
    return
  fi
  ensure_curl
  log 'installing Cursor CLI via cursor.com/install'
  curl https://cursor.com/install -fsS | bash
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap.sh [tool...]

Supported tools:
  bun
  uv
  lk
  claude
  codex
  cursor

When no tool list is provided, bootstrap installs the base RepoLine prerequisites:
  bun uv lk
EOF
}

normalize_tool() {
  case "$1" in
    livekit)
      printf 'lk\n'
      ;;
    cursor-agent)
      printf 'cursor\n'
      ;;
    *)
      printf '%s\n' "$1"
      ;;
  esac
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "$#" -eq 0 ]]; then
  set -- bun uv lk
fi

for raw_tool in "$@"; do
  tool="$(normalize_tool "$raw_tool")"
  case "$tool" in
    bun)
      install_bun
      ;;
    uv)
      install_uv
      ;;
    lk)
      install_lk
      ;;
    claude)
      install_claude
      ;;
    codex)
      install_codex
      ;;
    cursor)
      install_cursor
      ;;
    *)
      usage
      fail "unsupported tool: $raw_tool"
      ;;
  esac
done

log 'bootstrap complete'
