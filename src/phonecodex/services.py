from __future__ import annotations

from pathlib import Path


def systemd_unit_text(name: str, exec_args: list[str], service_path: str, env_file: Path) -> str:
    quoted = " ".join(exec_args)
    return f"""[Unit]
Description={name}
After=default.target

[Service]
Type=simple
Environment=PATH={service_path}
Environment=PHONECODEX_ENV_FILE={env_file}
EnvironmentFile=-{env_file}
ExecStart={quoted}
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=default.target
"""


def launchd_plist_text(label: str, args: list[str], log_name: str, log_dir: Path, service_path: str, env_file: Path) -> str:
    args_xml = "\n".join(f"    <string>{arg}</string>" for arg in args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{service_path}</string>
    <key>PHONECODEX_ENV_FILE</key>
    <string>{env_file}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{log_dir / (log_name + ".out.log")}</string>
  <key>StandardErrorPath</key>
  <string>{log_dir / (log_name + ".err.log")}</string>
</dict>
</plist>
"""
