#!/usr/bin/env bash
set -euo pipefail

if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 tmux ttyd tailscale
  if dnf list --available cloudflared >/dev/null 2>&1; then
    sudo dnf install -y cloudflared
  fi
elif command -v apt >/dev/null 2>&1; then
  sudo apt update
  sudo apt install -y python3 python3-pip tmux tailscale
  if apt-cache show ttyd >/dev/null 2>&1; then
    sudo apt install -y ttyd
  else
    echo "ttyd is not available from this apt repository; install ttyd before continuing." >&2
  fi
  if apt-cache show cloudflared >/dev/null 2>&1; then
    sudo apt install -y cloudflared
  else
    echo "cloudflared is optional; install it separately for Cloudflare named tunnels." >&2
  fi
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --needed python tmux ttyd tailscale
  if pacman -Si cloudflared >/dev/null 2>&1; then
    sudo pacman -S --needed cloudflared
  fi
else
  echo "Install python3, tmux, ttyd, tailscale, and optionally cloudflared with your OS package manager." >&2
fi

python3 -m pip install --user .
phonecodex doctor
phonecodex service install --mode tailscale
