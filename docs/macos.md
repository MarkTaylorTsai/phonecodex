# macOS Setup

macOS is a fully supported PhoneCodex platform.

## Requirements

- Python 3.10+
- `tmux`
- `ttyd`
- `codex`, optional
- `tailscale`, optional but recommended
- `cloudflared`, optional for public named tunnels
- launchd user agents

Install with Homebrew:

```bash
brew install python tmux ttyd tailscale
brew install cloudflared
```

Install PhoneCodex:

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
```

## launchd Services

Install and start the index launch agent:

```bash
phonecodex service install --mode tailscale
```

Create a Codex session:

```bash
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
```

Launch agents are written under:

```text
~/Library/LaunchAgents/com.phonecodex.index.plist
~/Library/LaunchAgents/com.phonecodex.session.NAME.plist
~/Library/LaunchAgents/com.phonecodex.proxy.NAME.plist
```

Logs are written under:

```text
~/.config/phonecodex/logs/
```

Manage sessions:

```bash
phonecodex service start warp
phonecodex service stop warp
phonecodex service restart warp
phonecodex service status warp
```

`status` on macOS prints launchctl/log guidance because launchd does not expose
the same unit status interface as systemd.

## Service PATH

launchd does not inherit your interactive shell PATH. Homebrew paths must be
present in the service environment.

Apple Silicon:

```bash
export PHONECODEX_SERVICE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
```

Intel:

```bash
export PHONECODEX_SERVICE_PATH="/usr/local/bin:/opt/homebrew/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
phonecodex service install --mode tailscale
```

Run `phonecodex doctor` to check whether `tmux`, `ttyd`, `tailscale`,
`cloudflared`, and `codex` are visible through that service PATH.

Proxy auth can be read from `~/.config/phonecodex/env`. Create it with:

```bash
phonecodex auth init --user phonecodex --generate
```

## Deployment Examples

Tailscale direct:

```bash
phonecodex codex warp ~/Source/Repo/warp --mode tailscale
phonecodex verify warp
```

Tailscale Serve:

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

Cloudflare mode keeps `ttyd`, the API, and the proxy bound to localhost. The
named tunnel should point only to the proxy port.
