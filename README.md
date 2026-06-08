# PhoneCodex

PhoneCodex lets a phone open and control local `tmux` terminal sessions through `ttyd`.
It is designed for Codex-style agent work: each project can get its own tmux session,
its own browser port, and a mobile toolbar with `Esc`, arrows, `Ctrl-C`, paste, copy,
and an `Ask` button that pastes text and presses Enter.

The default networking model is Tailscale. PhoneCodex binds to the Tailscale IP when
available, so the terminal is reachable from your phone without exposing the port to
the public internet.

## What It Provides

- A `phonecodex` CLI for creating and exposing terminal sessions.
- A local index page, usually `http://<tailscale-ip>:7680/`, listing all sessions.
- One `ttyd` port per session, usually starting at `7681`.
- A mobile toolbar injected into the terminal page.
- Paste from phone clipboard through a textarea fallback when browser clipboard APIs
  are blocked.
- Linux systemd user services and macOS launchd helpers.
- Windows support through WSL2, which is the recommended Windows path for `tmux`,
  `ttyd`, and Codex CLI.

## Requirements

Required on the machine running Codex:

- Python 3.10+
- `tmux`
- `ttyd`
- Tailscale, recommended
- `codex`, optional but needed for `phonecodex codex ...`

Required on the phone:

- Tailscale logged into the same tailnet, or another route to the host/port.
- A mobile browser.

## Quick Start For An Agent

Use this when another agent is setting up the tool for a user:

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
phonecodex install
phonecodex codex my-project /path/to/project
phonecodex list
```

Then open the printed URL from the phone.

If the phone cannot use the automatic clipboard read, press `Paste`, long-press inside
the paste box, use the phone's Paste command, then press `Insert` or `Ask`.

## Linux

Install dependencies with your distro package manager. Examples:

```bash
# Fedora
sudo dnf install -y python3 tmux ttyd tailscale

# Debian/Ubuntu, if ttyd is available in your release
sudo apt update
sudo apt install -y python3 python3-pip tmux ttyd tailscale
```

Install PhoneCodex:

```bash
python3 -m pip install --user .
phonecodex install
phonecodex doctor
```

Create a normal shell session:

```bash
phonecodex add warp ~/Source/Repo/warp
```

Create a Codex session:

```bash
phonecodex codex warp-codex ~/Source/Repo/warp
```

Linux installs these user services:

- `phonecodex-index.service`
- `phonecodex@NAME.service`

Useful service commands:

```bash
systemctl --user status phonecodex-index.service
systemctl --user status phonecodex@warp-codex.service
systemctl --user restart phonecodex@warp-codex.service
```

## macOS

Install dependencies with Homebrew:

```bash
brew install python tmux ttyd tailscale
```

Install and start PhoneCodex:

```bash
python3 -m pip install --user .
phonecodex install
phonecodex codex warp-codex ~/Source/Repo/warp
```

PhoneCodex writes launchd files under `~/Library/LaunchAgents`.

## Windows

The supported Windows setup is WSL2. Run PhoneCodex inside WSL, not native Windows
PowerShell, because `tmux` and Codex terminal behavior are much more reliable there.

1. Install WSL2 and Ubuntu.
2. Install Tailscale on Windows or inside WSL.
3. Open Ubuntu and run:

```bash
sudo apt update
sudo apt install -y python3 python3-pip tmux
# Install ttyd from your distro, Homebrew on Linux, or a ttyd release package.
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
phonecodex install
phonecodex codex my-project /path/to/project
```

If Tailscale runs on Windows instead of WSL, make sure your phone can reach the WSL
port. Running Tailscale inside WSL is usually simpler for this tool.

## CLI Reference

```bash
phonecodex install [--index-port 7680]
phonecodex doctor
phonecodex add NAME [DIR] [--port PORT] [--codex]
phonecodex codex NAME [DIR] [--port PORT]
phonecodex expose NAME [DIR]
phonecodex list
phonecodex url NAME
phonecodex attach NAME
phonecodex stop NAME
phonecodex kill NAME
```

Hidden service commands:

```bash
phonecodex serve-index --port 7680
phonecodex run-session NAME
```

## Security Notes

- PhoneCodex defaults to binding on the Tailscale IPv4 address when available.
- If Tailscale is not available, it binds to `127.0.0.1`; set
  `PHONECODEX_BIND_HOST` if you intentionally want a LAN bind address.
- The toolbar API can send keys and paste text into tmux sessions. Keep it on a
  private network such as Tailscale.
- Do not expose these ports through public tunnels unless you add authentication in
  front of them.

## Project Layout

```text
src/phonecodex/
  cli.py       # CLI, service install, session creation
  config.py    # config paths, session JSON, bind host/port selection
  server.py    # index page, toolbar API, tmux paste/key/capture
  toolbar.py   # injected mobile toolbar JavaScript
  assets/      # vendored ttyd mobile index used by --index
```

## License

MIT. See `THIRD_PARTY_NOTICES.md` for the vendored `ttyd` browser asset used
to inject the toolbar without a separate frontend build step.
