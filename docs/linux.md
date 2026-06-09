# Linux Setup

Linux is a fully supported PhoneCodex platform.

## Requirements

- Python 3.10+
- `tmux`
- `ttyd`
- `codex`, optional
- `tailscale`, optional but recommended
- `cloudflared`, optional for public named tunnels
- systemd user services

Install examples:

```bash
# Fedora
sudo dnf install -y python3 python3-pip tmux ttyd tailscale

# Debian/Ubuntu, if ttyd exists in your release
sudo apt update
sudo apt install -y python3 python3-pip tmux ttyd tailscale

# Arch
sudo pacman -S --needed python tmux ttyd tailscale
```

Install PhoneCodex:

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
```

## systemd User Services

Install service files and start the index service:

```bash
phonecodex service install --mode tailscale
```

Create and start a Codex session:

```bash
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
```

Manage services:

```bash
phonecodex service start warp
phonecodex service status warp
phonecodex service logs warp
phonecodex service restart warp
phonecodex service stop warp
```

Equivalent systemd units:

```text
phonecodex-index.service
phonecodex-api.service
phonecodex@warp.service
phonecodex-session@warp.service
phonecodex-proxy@warp.service
```

If you need services to keep running after boot when the user has not logged in:

```bash
loginctl enable-linger "$USER"
```

## Service PATH

systemd user services do not inherit your interactive shell PATH. If `phonecodex
doctor` says a command is visible interactively but not in the service PATH,
reinstall services with:

```bash
export PHONECODEX_SERVICE_PATH="/usr/local/bin:/usr/bin:/bin"
phonecodex service install --mode tailscale
```

Include any directory that contains `tmux`, `ttyd`, `tailscale`, `cloudflared`,
or `codex`.

Proxy auth can be read from:

```text
~/.config/phonecodex/env
```

Create it with:

```bash
phonecodex auth init --user phonecodex --generate
```

## Deployment Examples

Local-only:

```bash
phonecodex service install --mode local
phonecodex codex local-warp ~/Source/Repo/warp --mode local
```

Tailscale direct:

```bash
phonecodex service install --mode tailscale
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
phonecodex verify warp
```

Tailscale Serve private proxy:

```bash
phonecodex deploy tailscale warp --serve
phonecodex service restart warp
tailscale serve status
```

Cloudflare named tunnel:

```bash
cloudflared tunnel login
cloudflared tunnel create phonecodex
phonecodex deploy cloudflare warp \
  --hostname phonecodex.example.com \
  --tunnel phonecodex \
  --route-dns
phonecodex service restart warp
cloudflared tunnel run phonecodex
```

Cloudflare points to the local PhoneCodex proxy, not directly to `ttyd` or the API.
