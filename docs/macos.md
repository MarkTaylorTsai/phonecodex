# macOS Setup

PhoneCodex uses launchd agents on macOS.

```bash
brew install python tmux ttyd tailscale
python3 -m pip install --user .
phonecodex install
phonecodex codex warp-codex ~/Source/Repo/warp
```

Launch agents are written to:

```text
~/Library/LaunchAgents/com.phonecodex.index.plist
~/Library/LaunchAgents/com.phonecodex.session.NAME.plist
```

