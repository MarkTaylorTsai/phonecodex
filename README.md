# PhoneCodex

PhoneCodex exposes `tmux` and Codex-style terminal sessions to a phone through
`ttyd`, with a mobile toolbar for cursor keys, control keys, capture, copy, and
phone clipboard paste.

It is meant to be installable by a human or another coding agent on a fresh
machine. The supported deployment paths are:

- `local`: localhost-only testing.
- `tailscale`: private tailnet access, optionally through Tailscale Serve.
- `cloudflare`: permanent public hostname through a Cloudflare named tunnel.

PhoneCodex does not directly expose `ttyd` or the API in public mode. Public
traffic goes through the PhoneCodex auth proxy:

```text
browser -> Cloudflare tunnel or Tailscale Serve -> PhoneCodex proxy -> ttyd
                                                       |
                                                       +-> /api/* toolbar API
```

## Platform Strategy

macOS is fully supported with Python 3.10+, `tmux`, `ttyd`, optional `codex`,
optional `tailscale`, optional `cloudflared`, and launchd persistence.

Linux is fully supported with Python 3.10+, `tmux`, `ttyd`, optional `codex`,
optional `tailscale`, optional `cloudflared`, and systemd user services.

Windows support is WSL2-first. Install and run PhoneCodex inside Ubuntu or
Debian WSL2. Native Windows terminal hosting is only a limited fallback; do not
assume native Windows + `ttyd` + `tmux` + Codex TUI will behave reliably.

## Install

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
```

Install service files:

```bash
phonecodex install --mode tailscale
```

Create a Codex session:

```bash
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
phonecodex verify warp
phonecodex list
```

Open the printed URL from the phone. If browser clipboard read is blocked, press
`Paste`, long-press in the paste box, use the phone paste command, then press
`Insert` or `Ask`.

## Deployment Modes

### Local Mode

Local mode binds everything to `127.0.0.1`. Use it to test on the host machine.

```bash
phonecodex install --mode local
phonecodex codex local-warp ~/Source/Repo/warp --mode local
phonecodex verify local-warp
```

Local mode with the same proxy path used by public deployments:

```bash
phonecodex add local-proxy ~/Source/Repo/warp --mode local --proxy --auth-user phonecodex
phonecodex run-proxy local-proxy
phonecodex url local-proxy
```

### Tailscale Mode

Direct Tailscale mode binds `ttyd` and the toolbar API to the machine's
Tailscale IPv4 address. The phone must be in the same tailnet or allowed by
Tailscale sharing/ACLs.

```bash
phonecodex install --mode tailscale
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
phonecodex doctor
phonecodex verify warp
```

PhoneCodex reports the Tailscale IP and MagicDNS name when available. Typical
URLs look like:

```text
http://100.x.y.z:7681/
http://machine-name.tailnet.ts.net:7681/
```

Tailscale Serve is the preferred private reverse-proxy mode. It keeps `ttyd` and
the API on localhost, exposes only the PhoneCodex proxy to the tailnet, and is
not Funnel.

```bash
phonecodex deploy tailscale warp --serve
phonecodex service restart warp
tailscale serve status
```

When MagicDNS is enabled, the URL is usually:

```text
https://machine-name.tailnet.ts.net/
```

### Cloudflare Permanent Mode

Cloudflare production use requires a named tunnel and a fixed hostname. Do not
use `trycloudflare` quick tunnels or `localhost.run` as a permanent deployment;
those URLs are temporary and can later show `no tunnel here`.

Create a named tunnel with Cloudflare:

```bash
cloudflared tunnel login
cloudflared tunnel create phonecodex
```

Create or convert a session:

```bash
phonecodex codex warp ~/Source/Repo/warp \
  --mode cloudflare \
  --cloudflare-hostname phonecodex.example.com \
  --cloudflare-tunnel phonecodex \
  --auth-user phonecodex
```

Or deploy an existing session:

```bash
phonecodex deploy cloudflare warp \
  --hostname phonecodex.example.com \
  --tunnel phonecodex \
  --route-dns
```

`deploy cloudflare` patches `~/.cloudflared/config.yml` by adding an ingress rule
to the PhoneCodex local proxy:

```yaml
ingress:
  - hostname: phonecodex.example.com
    service: http://127.0.0.1:8781
  - service: http_status:404
```

Run the tunnel:

```bash
cloudflared tunnel run phonecodex
```

In Cloudflare mode:

- `ttyd` binds `127.0.0.1`.
- the API binds `127.0.0.1`.
- the PhoneCodex proxy binds `127.0.0.1`.
- Cloudflare points only to the proxy port.
- the mobile toolbar calls `location.origin`, so `/api/*` and `/mobile-toolbar.js`
  are served through the same authenticated origin as the terminal.

## Services

PhoneCodex installs native user services.

Linux:

```bash
phonecodex service install --mode tailscale
phonecodex service start warp
phonecodex service status warp
phonecodex service logs warp
phonecodex service restart warp
phonecodex service stop warp
```

If the service must run after boot without an interactive login:

```bash
loginctl enable-linger "$USER"
```

macOS:

```bash
phonecodex service install --mode tailscale
phonecodex service start warp
phonecodex service stop warp
```

launchd logs are under `~/.config/phonecodex/logs`.

Services include a configurable PATH because launchd and systemd user services do
not inherit your interactive shell PATH:

```bash
export PHONECODEX_SERVICE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
```

`phonecodex doctor` checks whether `tmux`, `ttyd`, `tailscale`, `cloudflared`,
and `codex` are visible both interactively and through the configured service
PATH.

## CLI Reference

```bash
phonecodex doctor
phonecodex install [--mode local|tailscale|cloudflare] [--index-port 7680] [--bind-host HOST]
phonecodex add NAME [DIR] [--mode MODE] [--proxy] [--port PORT] [--proxy-port PORT]
phonecodex codex NAME [DIR] [--mode MODE] [--proxy] [--auth-user USER] [--auth-password PASS]
phonecodex expose NAME [DIR] [--mode MODE]
phonecodex list
phonecodex url NAME
phonecodex verify NAME [--auth-password PASS]
phonecodex attach NAME
phonecodex stop NAME
phonecodex kill NAME
phonecodex service install|start|stop|restart|status|logs [NAME]
phonecodex deploy local NAME [--proxy]
phonecodex deploy tailscale NAME [--serve]
phonecodex deploy cloudflare NAME --hostname HOST --tunnel TUNNEL [--config PATH] [--route-dns]
```

Service entry points:

```bash
phonecodex serve-index --bind-host HOST --port 7680
phonecodex run-session NAME
phonecodex run-proxy NAME
```

## Security Notes

- The toolbar API can send keys, paste text, and capture terminal output.
- Keep local and Tailscale direct deployments private.
- Cloudflare mode creates or requires proxy Basic auth; store the generated
  password somewhere safe because only the hash is kept in the session config.
- Do not publish raw `ttyd` or the raw API port.
- Tailscale Serve is private tailnet exposure. Tailscale Funnel is public internet
  exposure and is not the default PhoneCodex path.
- Quick tunnels are only for demos and are not permanent infrastructure.

## Troubleshooting

Buttons render but do nothing:

```bash
phonecodex verify NAME
```

For proxy/public modes, the generated terminal page must contain:

```text
window.PHONECODEX_API_BASE = location.origin
```

The proxy must route:

```text
/api/*             -> PhoneCodex API server
/mobile-toolbar.js -> PhoneCodex API server
terminal HTTP/WS   -> ttyd
```

Terminal shows `Press Enter to Reconnect`:

- Do not use `ttyd` built-in auth in public mode.
- Use `phonecodex run-proxy NAME` for auth.
- Keep `ttyd` bound to `127.0.0.1` behind the proxy.

Paste returns OK but Codex does not receive text:

- Update to this version.
- PhoneCodex now targets `tmux` pane `NAME:0.0`.
- Paste uses `tmux send-keys -l` in chunks by default, with paste-buffer as a
  fallback.

Services cannot find commands:

```bash
phonecodex doctor
export PHONECODEX_SERVICE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
```

## Project Layout

```text
src/phonecodex/
  cli.py       # CLI, deploy, service install, session creation
  config.py    # config paths, session JSON, bind host/port selection
  proxy.py     # authenticated reverse proxy for public/proxy modes
  server.py    # index page, toolbar API, tmux key/paste/capture
  toolbar.py   # injected mobile toolbar JavaScript
  assets/      # vendored ttyd mobile index used by --index
```

## License

MIT. See `THIRD_PARTY_NOTICES.md` for the vendored `ttyd` browser asset used to
inject the toolbar without a separate frontend build step.
