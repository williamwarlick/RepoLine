#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/cursor-app-bridge-extension"
DEST_DIR="$HOME/.cursor/extensions/repoline.cursor-app-bridge-0.0.1"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "Missing source extension directory: $SRC_DIR" >&2
  exit 1
fi

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
rsync -a --delete "$SRC_DIR/" "$DEST_DIR/"

echo "Installed RepoLine Cursor bridge extension to $DEST_DIR"
