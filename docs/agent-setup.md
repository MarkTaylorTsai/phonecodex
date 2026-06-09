# Agent Setup Runbook

Use this runbook when an agent is asked to install PhoneCodex on a user's
machine. Make the smallest change that gives the user a working phone URL.

## 1. Read-Only Checks

```bash
python3 --version
command -v tmux || true
command -v ttyd || true
command -v tailscale || true
command -v cloudflared || true
command -v codex || true
phonecodex doctor 2>/dev/null || true
```

If the repo is not installed yet:

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
phonecodex verify --local-test
```

## 2. Pick The Deployment Mode

Use `local` only for host-machine tests:

```bash
phonecodex service install --mode local
phonecodex codex test-session /path/to/project --mode local
```

Use `tailscale` when the phone is in the same tailnet:

```bash
phonecodex service install --mode tailscale
phonecodex codex project-name /path/to/project --mode tailscale
```

Use Tailscale Serve when you want one stable tailnet HTTPS origin and proxy
routing for both terminal and toolbar API:

```bash
phonecodex auth init --user phonecodex --generate
phonecodex deploy tailscale project-name --serve
phonecodex service restart project-name
```

Use Cloudflare only with a named tunnel and fixed hostname:

```bash
cloudflared tunnel create phonecodex
phonecodex auth init --user phonecodex --generate
phonecodex deploy cloudflare project-name \
  --hostname phonecodex.example.com \
  --tunnel phonecodex \
  --route-dns
phonecodex service restart project-name
```

Do not use `trycloudflare` quick tunnels or `localhost.run` as the final answer.
They are temporary demo routes.

## 3. Verify

```bash
phonecodex list
phonecodex url project-name
phonecodex verify project-name
phonecodex verify --local-test
```

For authenticated proxy sessions:

```bash
phonecodex verify project-name --auth-password 'the-password'
```

Expected important checks:

```text
ok generated mobile index
ok index contains inline toolbar
ok index pins session name
ok toolbar has Paste/Insert/Ask
ok toolbar has arrow keys
ok proxy API base is origin
```

## 4. Service Commands

Linux:

```bash
phonecodex service status project-name
phonecodex service logs project-name
phonecodex service restart project-name
```

macOS:

```bash
phonecodex service restart project-name
ls ~/.config/phonecodex/logs
```

WSL2 without systemd:

```bash
phonecodex serve-index --bind-host 127.0.0.1 --port 7680
phonecodex run-session project-name
phonecodex run-proxy project-name
```

## 5. Troubleshooting

Toolbar missing:

```bash
phonecodex verify project-name
phonecodex stop project-name
phonecodex codex project-name /path/to/project --mode tailscale
```

Toolbar buttons render but do nothing:

- In proxy/public modes, confirm the generated HTML uses `location.origin`.
- Confirm the proxy is running.
- Confirm `/api/*` and `/mobile-toolbar.js` go through the proxy, not a hard-coded
  `:7680` API origin.

`Press Enter to Reconnect`:

- Remove `ttyd` built-in auth from public paths.
- Use `phonecodex run-proxy NAME` for auth.
- Keep `ttyd` bound to `127.0.0.1` behind the proxy.

Service cannot find commands:

```bash
phonecodex doctor
export PHONECODEX_SERVICE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
```

Paste API returns OK but no text appears:

- Update PhoneCodex and restart the session.
- The current paste path targets `NAME:0.0` and sends literal keystrokes with
  `tmux send-keys -l`.
