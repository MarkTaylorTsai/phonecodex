# Windows Setup

Use WSL2. Native Windows terminal hosting is not the primary target because this tool
depends on `tmux` and Unix-like process behavior.

PowerShell:

```powershell
wsl --install -d Ubuntu
```

After reboot, open Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-pip tmux
git clone https://github.com/MarkTaylorTsai/phonecodex.git
cd phonecodex
python3 -m pip install --user .
phonecodex doctor
phonecodex install
phonecodex codex my-project /path/to/project
```

Run Tailscale inside WSL or make sure Windows forwards the WSL port to the network
your phone can reach.
