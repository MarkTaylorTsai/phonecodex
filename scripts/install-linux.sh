#!/usr/bin/env bash
set -euo pipefail

if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 tmux ttyd tailscale
elif command -v apt >/dev/null 2>&1; then
  sudo apt update
  sudo apt install -y python3 python3-pip tmux tailscale
  if apt-cache show ttyd >/dev/null 2>&1; then
    sudo apt install -y ttyd
  else
    echo "ttyd is not available from this apt repository; install ttyd before continuing." >&2
  fi
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --needed python tmux ttyd tailscale
else
  echo "Install python3, tmux, ttyd, and tailscale with your OS package manager." >&2
fi

python3 -m pip install --user .
phonecodex install
phonecodex doctor

