# Linux Setup

PhoneCodex uses systemd user services on Linux.

```bash
python3 -m pip install --user .
phonecodex install
phonecodex codex warp-codex ~/Source/Repo/warp
```

Check services:

```bash
systemctl --user status phonecodex-index.service
systemctl --user status phonecodex@warp-codex.service
```

If services do not start after reboot, enable lingering:

```bash
loginctl enable-linger "$USER"
```

