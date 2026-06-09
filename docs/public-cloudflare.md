# Cloudflare Permanent Deployment

Cloudflare mode uses a named tunnel and a fixed hostname. Quick tunnels are only
for demos and are not permanent.

## Architecture

```text
Cloudflare named tunnel -> http://127.0.0.1:PROXY_PORT -> PhoneCodex proxy
                                                         -> ttyd localhost
                                                         -> API localhost
```

Do not point Cloudflare directly at `ttyd` or the API server.

## Setup

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
  --cloudflared-config ~/.cloudflared/config.yml \
  --route-dns
phonecodex service restart warp
cloudflared tunnel run phonecodex
```

`deploy cloudflare` patches ingress:

```yaml
ingress:
  - hostname: phonecodex.example.com
    service: http://127.0.0.1:8781
  - service: http_status:404
```

## Verify

```bash
phonecodex verify warp --auth-password "$PHONECODEX_AUTH_PASSWORD"
curl -i https://phonecodex.example.com/
curl -i -u phonecodex:"$PHONECODEX_AUTH_PASSWORD" https://phonecodex.example.com/
```

Expected:

- no auth returns `401`;
- auth returns `200`;
- terminal HTML contains `pcx-toolbar`;
- generated HTML contains `window.PHONECODEX_API_BASE = location.origin`.

## Notes

- `cloudflared tunnel route dns <tunnel> <hostname>` is run when `--route-dns`
  is passed.
- Restart or rerun `cloudflared tunnel run <tunnel>` after changing ingress.
- `phonecodex deploy cloudflare multi ...` creates multiple hostnames and ingress
  rules.
