# PhoneCodex

PhoneCodex exposes `tmux` and Codex-style terminal sessions to a phone through
`ttyd`, with a mobile toolbar for cursor keys, control keys, capture, copy, and
phone clipboard paste.

The productized deployment paths are:

- `local`: localhost-only development and verification.
- `tailscale`: private tailnet access through a Tailscale IP, MagicDNS, or Tailscale Serve.
- `cloudflare`: permanent public hostname through a Cloudflare named tunnel.

Public/proxy deployments use this shape:

```text
phone/browser -> Tailscale Serve or Cloudflare named tunnel -> PhoneCodex proxy -> ttyd
                                                                  |
                                                                  +-> /api/* toolbar API
```

Do not directly publish raw `ttyd` or the raw API server.

## Install

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
```

Optional but recommended for proxy/public deployments:

```bash
phonecodex auth init --user phonecodex --generate
```

This creates `~/.config/phonecodex/env` with mode `600`. Services also read this
file. You can create it manually:

```bash
PHONECODEX_AUTH_USER=phonecodex
PHONECODEX_AUTH_PASSWORD=change-this-long-password
```

## Quick Start Local

Local mode binds `ttyd`, the API, and the proxy to `127.0.0.1`.

```bash
phonecodex service install --mode local
phonecodex codex local-warp ~/Source/Repo/warp --mode local
phonecodex verify local-warp
```

Run the full local integration test:

```bash
phonecodex verify --local-test
```

That test creates a temporary tmux session, API server, ttyd server, and auth
proxy, then verifies 401/200 auth behavior, toolbar HTML, `/api/session`,
`/api/key`, and `/api/paste` into tmux capture.

## Quick Start Tailscale

Direct private Tailscale:

```bash
phonecodex service install --mode tailscale
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
phonecodex verify warp
phonecodex list
```

Private proxy through Tailscale Serve:

```bash
phonecodex auth init --user phonecodex --generate
phonecodex deploy tailscale warp --serve
phonecodex service restart warp
tailscale serve status
```

Tailscale Serve is private tailnet exposure, not Funnel. The phone must be in
the same tailnet or allowed by Tailscale sharing/ACLs.

See [docs/tailscale.md](docs/tailscale.md).

## Quick Start Cloudflare Permanent

Use a named tunnel and a fixed hostname. Do not use `trycloudflare` quick tunnels
or `localhost.run` as permanent deployments.

```bash
cloudflared tunnel login
cloudflared tunnel create phonecodex
phonecodex auth init --user phonecodex --generate
phonecodex codex warp ~/Source/Repo/warp --mode cloudflare \
  --cloudflare-hostname phonecodex.example.com \
  --cloudflare-tunnel phonecodex \
  --auth-user phonecodex
phonecodex deploy cloudflare warp \
  --hostname phonecodex.example.com \
  --tunnel phonecodex \
  --route-dns
phonecodex service restart warp
cloudflared tunnel run phonecodex
```

Cloudflare points to the PhoneCodex local proxy, not directly to `ttyd` or the
API. The generated toolbar uses `window.PHONECODEX_API_BASE = location.origin`,
so buttons and paste use the same authenticated public origin as the terminal.

See [docs/public-cloudflare.md](docs/public-cloudflare.md).

## Quick Start Multiple Sessions

Create six Cloudflare-backed sessions and ingress rules:

```bash
phonecodex deploy cloudflare multi \
  --tunnel phonecodex \
  --base-hostname phonecodex.example.com \
  --count 6 \
  --start-port 7681 \
  --start-proxy-port 7690 \
  --directory ~/Source/Repo/warp \
  --route-dns
```

This creates:

```text
phonecodex     -> https://phonecodex.example.com
phonecodex-2   -> https://phonecodex2.example.com
phonecodex-3   -> https://phonecodex3.example.com
...
```

See [docs/multi-session.md](docs/multi-session.md).

## Platform Support

macOS is fully supported with Python 3.10+, `tmux`, `ttyd`, optional `codex`,
optional `tailscale`, optional `cloudflared`, and launchd services.

Linux is fully supported with Python 3.10+, `tmux`, `ttyd`, optional `codex`,
optional `tailscale`, optional `cloudflared`, and systemd user services.

Windows support is WSL2-first. Run PhoneCodex inside Ubuntu or Debian WSL2.
Native Windows support is experimental and not the recommended path for Codex
TUI + `ttyd` + `tmux`.

See:

- [docs/macos.md](docs/macos.md)
- [docs/linux.md](docs/linux.md)
- [docs/windows-wsl.md](docs/windows-wsl.md)

## Service Management

Linux systemd user services and macOS launchd agents:

```bash
phonecodex service install --mode tailscale
phonecodex service start NAME
phonecodex service status NAME
phonecodex service logs NAME
phonecodex service restart NAME
phonecodex service stop NAME
```

Linux users who need services after boot without login should enable lingering:

```bash
loginctl enable-linger "$USER"
```

Generated systemd units include backward-compatible names and productized names:

```text
phonecodex-index.service
phonecodex-api.service
phonecodex@NAME.service
phonecodex-session@NAME.service
phonecodex-proxy@NAME.service
```

Services include a configurable PATH and an env file:

```bash
export PHONECODEX_SERVICE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
```

## CLI Reference

```bash
phonecodex doctor
phonecodex auth init [--user phonecodex] [--generate] [--auth-password-env ENV]
phonecodex install [--mode local|tailscale|cloudflare]
phonecodex add NAME [DIR] [--mode MODE] [--proxy] [--port PORT] [--proxy-port PORT]
phonecodex codex NAME [DIR] [--mode MODE] [--proxy]
phonecodex list
phonecodex url NAME
phonecodex verify NAME [--auth-password PASS]
phonecodex verify --local-test
phonecodex attach NAME
phonecodex stop NAME
phonecodex kill NAME
phonecodex proxy run NAME [--proxy-port PORT] [--auth-password-env ENV]
phonecodex proxy install-service NAME [--proxy-port PORT] [--generate-auth]
phonecodex proxy verify NAME [--auth-password PASS]
phonecodex service install|start|stop|restart|status|logs [NAME]
phonecodex deploy local NAME [--proxy] [--proxy-port PORT]
phonecodex deploy tailscale NAME [--hostname HOST] [--serve] [--proxy-port PORT]
phonecodex deploy cloudflare NAME --hostname HOST --tunnel TUNNEL [--route-dns]
phonecodex deploy cloudflare multi --tunnel TUNNEL --base-hostname HOST --count N
```

Backward-compatible service entry points remain:

```bash
phonecodex serve-index --bind-host HOST --port 7680
phonecodex run-session NAME
phonecodex run-proxy NAME
```

## Security Notes

Do not:

- expose every local port to the internet;
- expose `ttyd` directly to the internet;
- expose the API server directly to the internet;
- run a public terminal without authentication;
- treat quick tunnels as permanent infrastructure.

Recommended public/private proxy architecture:

- `ttyd`: localhost only
- API: localhost only
- PhoneCodex proxy: localhost only for Cloudflare and Tailscale Serve
- Cloudflare/Tailscale: points to the proxy
- auth: Basic Auth at the proxy layer or stronger auth in front of it

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md).

Common checks:

```bash
phonecodex doctor
phonecodex verify NAME --auth-password "$PHONECODEX_AUTH_PASSWORD"
phonecodex verify --local-test
```

## Project Layout

```text
src/phonecodex/
  cli.py       # CLI, service install, deploy commands, verification
  config.py    # config paths, sessions, ports, env file helpers
  deploy.py    # Cloudflare ingress and multi-session helpers
  proxy.py     # authenticated HTTP/WebSocket reverse proxy
  server.py    # index page, toolbar API, tmux key/paste/capture
  services.py  # systemd and launchd templates
  toolbar.py   # injected mobile toolbar JavaScript
```

## License

MIT. See `THIRD_PARTY_NOTICES.md` for the vendored `ttyd` browser asset.
