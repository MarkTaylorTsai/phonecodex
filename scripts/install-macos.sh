#!/usr/bin/env bash
set -euo pipefail

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required for this installer: https://brew.sh" >&2
  exit 1
fi

brew install python tmux ttyd tailscale
python3 -m pip install --user .
phonecodex install
phonecodex doctor

