# Agent Setup Runbook

Use this runbook when an agent is asked to set up PhoneCodex on a user's machine.

## Read-Only Checks

```bash
python3 --version
command -v tmux || true
command -v ttyd || true
command -v tailscale || true
command -v codex || true
tailscale ip -4 2>/dev/null || true
```

## Install The Package

```bash
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
```

## Start Services

```bash
phonecodex install
```

## Add A Project

Shell only:

```bash
phonecodex add my-project /path/to/project
```

Codex:

```bash
phonecodex codex my-project /path/to/project
```

## Verify

```bash
phonecodex list
phonecodex url my-project
phonecodex verify my-project
```

On the phone, open the URL. Press `Paste`; if clipboard read is blocked, long-press in
the paste box, paste manually, then press `Insert` or `Ask`.

## Troubleshooting

- `ttyd command not found`: install `ttyd` with the OS package manager or from the
  upstream release package.
- Phone cannot connect: verify Tailscale is connected on both devices and that
  `phonecodex doctor` shows a Tailscale bind IP.
- Toolbar says `no session`: the terminal page port is not registered in
  `~/.config/phonecodex/sessions`.
- Paste fails: ensure the index service is running on port `7680`.
- Buttons are missing: run `phonecodex verify NAME`; if it does not report
  `ok running session page contains toolbar`, rerun `phonecodex install` and
  restart the session with
  `phonecodex stop NAME && phonecodex codex NAME /path/to/project`.
