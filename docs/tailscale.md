# Tailscale Deployment

Tailscale mode is the recommended private deployment path. It does not expose
PhoneCodex to the public internet.

## Direct Tailnet Mode

```bash
phonecodex service install --mode tailscale
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
phonecodex doctor
phonecodex verify warp
```

PhoneCodex uses the Tailscale IP when available. The phone must be in the same
tailnet or allowed by sharing/ACLs.

Typical URLs:

```text
http://100.x.y.z:7681/
http://machine-name.tailnet.ts.net:7681/
```

## Tailscale Serve

Serve gives a stable tailnet HTTPS origin and keeps `ttyd` plus the API on
localhost behind the PhoneCodex proxy.

```bash
phonecodex auth init --user phonecodex --generate
phonecodex deploy tailscale warp --serve
phonecodex service restart warp
tailscale serve status
```

Expected URL:

```text
https://machine-name.tailnet.ts.net/
```

This is Tailscale Serve, not Funnel. Funnel is public internet exposure and is
not PhoneCodex's default path.

## CLI Diagnostics

```bash
phonecodex doctor
tailscale status
tailscale ip -4
tailscale serve status
```

`doctor` reports whether `tailscale` is installed, the Tailscale IP, MagicDNS
name when available, and Serve status when the command is available.
