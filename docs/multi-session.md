# Multi-Session Deployment

PhoneCodex supports multiple independent sessions. Each session has:

- a tmux session;
- a ttyd port;
- an optional proxy port;
- an optional public hostname.

## Cloudflare Multi-Session

```bash
phonecodex auth init --user phonecodex --generate
phonecodex deploy cloudflare multi \
  --tunnel phonecodex \
  --base-hostname phonecodex.example.com \
  --count 6 \
  --start-port 7681 \
  --start-proxy-port 7690 \
  --directory ~/Source/Repo/warp \
  --route-dns
```

Created sessions:

```text
phonecodex     ttyd=7681 proxy=7690 hostname=phonecodex.example.com
phonecodex-2   ttyd=7682 proxy=7691 hostname=phonecodex2.example.com
phonecodex-3   ttyd=7683 proxy=7692 hostname=phonecodex3.example.com
```

Custom host pattern:

```bash
phonecodex deploy cloudflare multi \
  --tunnel phonecodex \
  --host-pattern 'phonecodex{n}.example.com' \
  --count 6 \
  --start-port 7681 \
  --start-proxy-port 7690 \
  --directory ~/Source/Repo/warp
```

## Verify

```bash
phonecodex list
phonecodex verify phonecodex --auth-password "$PHONECODEX_AUTH_PASSWORD"
phonecodex verify phonecodex-2 --auth-password "$PHONECODEX_AUTH_PASSWORD"
```

Restart services:

```bash
phonecodex service restart phonecodex
phonecodex service restart phonecodex-2
```

Run Cloudflare:

```bash
cloudflared tunnel run phonecodex
```
