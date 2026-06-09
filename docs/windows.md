# Windows Setup

PhoneCodex's supported Windows path is WSL2. Run the server, `tmux`, `ttyd`, and
Codex inside Ubuntu or Debian WSL2.

Native Windows is not the primary target. Native PowerShell plus terminal hosting
can be useful for other workflows, but PhoneCodex does not guarantee stable
native Windows behavior for Codex TUI + `ttyd` + `tmux`.

## Primary Path: WSL2

Install WSL2 from PowerShell:

```powershell
wsl --install -d Ubuntu
```

Open Ubuntu and install dependencies:

```bash
sudo apt update
sudo apt install -y python3 python3-pip tmux tailscale

# If your distro has ttyd:
sudo apt install -y ttyd
```

If `ttyd` is not available in your apt repository, install it from the upstream
release package or another trusted package source before continuing.

Install PhoneCodex:

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
phonecodex verify --local-test
```

For the newer detailed WSL2 runbook, see `docs/windows-wsl.md`.

## WSL2 With systemd

Recent WSL supports systemd. Check:

```bash
systemctl --user status
```

If systemd is available:

```bash
phonecodex service install --mode tailscale
phonecodex codex warp /path/to/project --mode tailscale
phonecodex verify warp
```

For Tailscale Serve:

```bash
phonecodex deploy tailscale warp --serve
phonecodex service restart warp
tailscale serve status
```

For Cloudflare:

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

## WSL2 Without systemd

If `systemctl --user` is not available, run services in foreground terminals:

```bash
phonecodex serve-index --bind-host 127.0.0.1 --port 7680
phonecodex run-session warp
```

For proxy modes, run a third terminal:

```bash
phonecodex run-proxy warp
```

Background fallback:

```bash
nohup phonecodex serve-index --bind-host 127.0.0.1 --port 7680 > ~/.config/phonecodex/index.log 2>&1 &
nohup phonecodex run-session warp > ~/.config/phonecodex/session-warp.log 2>&1 &
nohup phonecodex run-proxy warp > ~/.config/phonecodex/proxy-warp.log 2>&1 &
```

## Tailscale Location

The simplest setup is running Tailscale inside WSL2:

```bash
sudo tailscale up
phonecodex doctor
```

If Tailscale runs only on Windows, ensure the phone can actually reach WSL2's
listening ports. WSL networking behavior varies by Windows version, so this is
less predictable than running Tailscale in WSL.

## Optional Native Windows

Native Windows support is limited. If you insist on a native route, prefer:

- PowerShell or Windows Terminal for manual local work.
- OpenSSH server for remote shell access.
- WSL2 for PhoneCodex terminal hosting.
- Windows Task Scheduler or NSSM only for wrapper scripts that call into WSL.

Do not treat native Windows as equivalent to the macOS/Linux/WSL2 support path.
