# Troubleshooting

Start with:

```bash
phonecodex doctor
phonecodex verify NAME --auth-password "$PHONECODEX_AUTH_PASSWORD"
phonecodex verify --local-test
```

## Toolbar Appears But Buttons Do Nothing

Cause: the page loaded from `ttyd`, but `/api/*` is not routed to the PhoneCodex
API, or the toolbar uses a hard-coded `:7680` API origin.

Fix:

```bash
phonecodex verify NAME --auth-password "$PHONECODEX_AUTH_PASSWORD"
phonecodex proxy install-service NAME --generate-auth
phonecodex service restart NAME
```

In proxy/public modes, generated HTML must include:

```text
window.PHONECODEX_API_BASE = location.origin
```

The proxy must route:

```text
/api/*              -> PhoneCodex API server
/mobile-toolbar.js  -> PhoneCodex API server
terminal HTTP/WS    -> ttyd
```

## Page Loads But Terminal Reconnects

Cause: `ttyd` built-in auth can allow the HTML to load while blocking `/token`
or WebSocket handshake.

Fix:

- do not use `ttyd` built-in auth in public mode;
- use `phonecodex run-proxy NAME` or `phonecodex proxy install-service NAME`;
- keep `ttyd` bound to `127.0.0.1` behind the proxy.

## `no tunnel here`

Cause: a quick tunnel URL expired or was never permanent.

Fix:

- use Tailscale tailnet/Tailscale Serve; or
- use Cloudflare named tunnel:

```bash
cloudflared tunnel create phonecodex
phonecodex deploy cloudflare NAME --hostname phonecodex.example.com --tunnel phonecodex --route-dns
cloudflared tunnel run phonecodex
```

## Tailscale IP Cannot Connect

Check:

```bash
tailscale status
tailscale ip -4
phonecodex doctor
phonecodex list
```

Make sure the phone is logged into the same tailnet or allowed by sharing/ACLs.
If you use Tailscale Serve, check:

```bash
tailscale serve status
```

## launchd/systemd Command Not Found

Services do not inherit your shell PATH.

```bash
phonecodex doctor
export PHONECODEX_SERVICE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
phonecodex service restart NAME
```

Linux:

```bash
loginctl enable-linger "$USER"
```

## Cloudflare 502/404

Check:

```bash
cloudflared tunnel list
cloudflared tunnel route dns phonecodex phonecodex.example.com
cat ~/.cloudflared/config.yml
phonecodex service restart NAME
cloudflared tunnel run phonecodex
```

The ingress rule must point to the PhoneCodex proxy:

```yaml
- hostname: phonecodex.example.com
  service: http://127.0.0.1:8781
```

## Codex First-Run Model Selection

If Codex shows a first-run model or login prompt, attach from the desktop once:

```bash
phonecodex attach NAME
```

Complete the prompt, then reopen the phone URL.

## API Returns OK But Terminal Unchanged

Older PhoneCodex versions used `tmux paste-buffer`, which can be swallowed by
full-screen TUIs. Current PhoneCodex targets `NAME:0.0` and sends literal
keystrokes with `tmux send-keys -l` by default.

Verify:

```bash
phonecodex verify --local-test
```

Restart the session after upgrading:

```bash
phonecodex service restart NAME
```
