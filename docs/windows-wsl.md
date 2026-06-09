# Windows WSL2 Setup

PhoneCodex's supported Windows path is WSL2. Run PhoneCodex, `tmux`, `ttyd`, and
Codex inside Ubuntu or Debian WSL2.

Native Windows support is experimental. Do not assume native Windows + Codex TUI
+ `ttyd` + `tmux` is stable.

## Install WSL2

PowerShell:

```powershell
wsl --install -d Ubuntu
```

Open Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-pip tmux tailscale
sudo apt install -y ttyd  # if available in your apt repository
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
```

Install `cloudflared` separately if you need Cloudflare named tunnels.

## WSL2 With systemd

```bash
systemctl --user status
phonecodex service install --mode tailscale
phonecodex codex warp /path/to/project --mode tailscale
phonecodex verify warp
```

If Tailscale runs inside WSL2:

```bash
sudo tailscale up
phonecodex doctor
```

## WSL2 Without systemd

Run foreground commands in separate WSL terminals:

```bash
phonecodex serve-index --bind-host 127.0.0.1 --port 7680
phonecodex run-session warp
phonecodex run-proxy warp
```

Background fallback:

```bash
mkdir -p ~/.config/phonecodex
nohup phonecodex serve-index --bind-host 127.0.0.1 --port 7680 > ~/.config/phonecodex/api.log 2>&1 &
nohup phonecodex run-session warp > ~/.config/phonecodex/session-warp.log 2>&1 &
nohup phonecodex run-proxy warp > ~/.config/phonecodex/proxy-warp.log 2>&1 &
```

## Optional Native Windows

For native Windows, prefer PowerShell, Windows Terminal, OpenSSH server, or WSL2.
Task Scheduler or NSSM can wrap `wsl.exe`, but this is not the main PhoneCodex
support path.
