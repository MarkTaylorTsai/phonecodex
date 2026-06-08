from __future__ import annotations

import argparse
import importlib.resources
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import (
    DEFAULT_INDEX_PORT,
    SessionConfig,
    all_sessions,
    choose_port,
    command_exists,
    config_dir,
    default_bind_host,
    display_host,
    ensure_dirs,
    mobile_index_path,
    python_command,
    read_session,
    session_path,
    validate_name,
    write_session,
)
from .server import serve_index


def die(message: str) -> None:
    raise SystemExit(f"phonecodex: {message}")


def run(command: list[str], *, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    return subprocess.run(command, check=check, text=True, stdout=stdout, stderr=stderr)


def ensure_mobile_index(index_port: int = DEFAULT_INDEX_PORT) -> Path:
    ensure_dirs()
    try:
        source = importlib.resources.files("phonecodex.assets").joinpath("mobile-index.html")
        html = source.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        html = "<!doctype html><html><body><pre>mobile-index.html asset is missing</pre></body></html>"

    replacement = f":{index_port}/mobile-toolbar.js"
    if "/mobile-toolbar.js" in html:
        html = re.sub(r":[0-9]+/mobile-toolbar\.js", replacement, html)
    else:
        script = (
            "<script>(function(){"
            "var s=document.createElement('script');"
            f"s.src=location.protocol+'//'+location.hostname+':{index_port}/mobile-toolbar.js';"
            "s.defer=true;document.body.appendChild(s);"
            "})();</script>"
        )
        html = html.replace("</body>", script + "</body>")

    path = mobile_index_path(index_port)
    path.write_text(html, encoding="utf-8")
    return path


def unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def install_systemd(index_port: int, *, start_index: bool) -> None:
    ensure_dirs()
    ensure_mobile_index(index_port)
    unit_dir().mkdir(parents=True, exist_ok=True)
    python = python_command()
    session_unit = f"""[Unit]
Description=PhoneCodex mobile terminal session (%i)
After=default.target

[Service]
Type=simple
ExecStart={python} -m phonecodex run-session %i
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=default.target
"""
    index_unit = f"""[Unit]
Description=PhoneCodex mobile terminal index and toolbar API
After=default.target

[Service]
Type=simple
ExecStart={python} -m phonecodex serve-index --port {index_port}
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=default.target
"""
    (unit_dir() / "phonecodex@.service").write_text(session_unit, encoding="utf-8")
    (unit_dir() / "phonecodex-index.service").write_text(index_unit, encoding="utf-8")
    if command_exists("systemctl"):
        run(["systemctl", "--user", "daemon-reload"])
        if start_index:
            run(["systemctl", "--user", "enable", "--now", "phonecodex-index.service"])


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist(label: str, args: list[str], log_name: str) -> str:
    args_xml = "\n".join(f"    <string>{arg}</string>" for arg in args)
    log_dir = config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
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


def install_launchd(index_port: int, *, start_index: bool) -> None:
    ensure_dirs()
    ensure_mobile_index(index_port)
    launch_agents_dir().mkdir(parents=True, exist_ok=True)
    path = launch_agents_dir() / "com.phonecodex.index.plist"
    path.write_text(
        plist(
            "com.phonecodex.index",
            [python_command(), "-m", "phonecodex", "serve-index", "--port", str(index_port)],
            "index",
        ),
        encoding="utf-8",
    )
    if start_index and command_exists("launchctl"):
        run(["launchctl", "unload", str(path)], check=False, quiet=True)
        run(["launchctl", "load", str(path)])


def install_services(index_port: int, *, start_index: bool = True) -> None:
    system = platform.system().lower()
    if system == "linux":
        install_systemd(index_port, start_index=start_index)
    elif system == "darwin":
        install_launchd(index_port, start_index=start_index)
    elif system == "windows":
        print("Windows support is via WSL2. Run these commands inside WSL Ubuntu.")
    else:
        print("Unsupported service manager. Use phonecodex serve-index and phonecodex run-session manually.")


def start_index_service(index_port: int) -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        if not (unit_dir() / "phonecodex-index.service").exists():
            install_systemd(index_port, start_index=False)
        run(["systemctl", "--user", "enable", "--now", "phonecodex-index.service"])
    elif system == "darwin" and command_exists("launchctl"):
        if not (launch_agents_dir() / "com.phonecodex.index.plist").exists():
            install_launchd(index_port, start_index=False)
        run(["launchctl", "load", str(launch_agents_dir() / "com.phonecodex.index.plist")], check=False)


def start_session_service(session: SessionConfig) -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        if not (unit_dir() / "phonecodex@.service").exists():
            install_systemd(session.index_port, start_index=False)
        run(["systemctl", "--user", "enable", "--now", f"phonecodex@{session.name}.service"])
    elif system == "darwin" and command_exists("launchctl"):
        launch_agents_dir().mkdir(parents=True, exist_ok=True)
        label = f"com.phonecodex.session.{session.name}"
        path = launch_agents_dir() / f"{label}.plist"
        path.write_text(
            plist(label, [python_command(), "-m", "phonecodex", "run-session", session.name], f"session-{session.name}"),
            encoding="utf-8",
        )
        run(["launchctl", "unload", str(path)], check=False, quiet=True)
        run(["launchctl", "load", str(path)])
    else:
        print(f"Run manually: phonecodex run-session {session.name}")


def stop_session_service(name: str) -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        run(["systemctl", "--user", "disable", "--now", f"phonecodex@{name}.service"], check=False, quiet=True)
    elif system == "darwin" and command_exists("launchctl"):
        label = f"com.phonecodex.session.{name}"
        path = launch_agents_dir() / f"{label}.plist"
        if path.exists():
            run(["launchctl", "unload", str(path)], check=False, quiet=True)


def ensure_tmux_session(name: str, workdir: Path, initial_command: str = "") -> None:
    if not command_exists("tmux"):
        die("tmux command not found")
    exists = subprocess.run(["tmux", "has-session", "-t", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if exists.returncode == 0:
        return
    run(["tmux", "new-session", "-d", "-s", name, "-c", str(workdir)])
    if initial_command:
        run(["tmux", "send-keys", "-t", name, initial_command, "C-m"])


def create_session(args: argparse.Namespace, *, codex: bool = False, expose: bool = False) -> None:
    name = args.name
    validate_name(name)
    existing = None
    if session_path(name).exists():
        existing = read_session(name)

    workdir = Path(args.directory or os.getcwd()).expanduser()
    if expose and not args.directory:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", name, "#{pane_current_path}"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.stdout.strip():
            workdir = Path(result.stdout.strip())
    if not workdir.exists() or not workdir.is_dir():
        die(f"directory does not exist: {workdir}")
    workdir = workdir.resolve()

    if codex and not command_exists("codex"):
        die("codex command not found in PATH")

    port = args.port or choose_port(existing)
    title = args.title or (f"{name} codex" if codex else name)
    session = SessionConfig(
        name=name,
        port=int(port),
        title=title,
        tmux_session=name,
        workdir=str(workdir),
        index_port=args.index_port,
    )
    write_session(session)
    ensure_mobile_index(args.index_port)

    if not args.no_tmux:
        ensure_tmux_session(name, workdir, "codex" if codex else "")

    if not args.no_start:
        start_index_service(args.index_port)
        start_session_service(session)

    print(f"{session.name}  http://{display_host()}:{session.port}/  {session.workdir}")


def cmd_install(args: argparse.Namespace) -> None:
    install_services(args.index_port, start_index=not args.no_start)
    print(f"config: {config_dir()}")
    print(f"index:  http://{display_host()}:{args.index_port}/")


def cmd_add(args: argparse.Namespace) -> None:
    create_session(args, codex=args.codex)


def cmd_codex(args: argparse.Namespace) -> None:
    create_session(args, codex=True)


def cmd_expose(args: argparse.Namespace) -> None:
    create_session(args, expose=True)


def cmd_list(args: argparse.Namespace) -> None:
    host = display_host()
    print(f"{'NAME':18} {'PORT':6} {'URL':30} DIR")
    for session in all_sessions():
        print(f"{session.name:18} {session.port:<6} http://{host}:{session.port}/{'':3} {session.workdir}")


def cmd_url(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    print(f"http://{display_host()}:{session.port}/")


def cmd_attach(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    os.environ["PHONECODEX_WORKDIR"] = session.workdir
    os.execvp("tmux", ["tmux", "new-session", "-A", "-s", session.tmux_session, "-c", session.workdir])


def cmd_run_session(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    if not command_exists("ttyd"):
        die("ttyd command not found")
    index = ensure_mobile_index(session.index_port)
    bind_host = args.bind_host or default_bind_host()
    command = [
        "ttyd",
        "--interface",
        bind_host,
        "--port",
        str(session.port),
        "--index",
        str(index),
        "--writable",
        "--check-origin",
        "--client-option",
        f"titleFixed={session.title}",
        "--client-option",
        "fontSize=14",
        "--client-option",
        "cursorBlink=true",
        python_command(),
        "-m",
        "phonecodex",
        "tmux-wrapper",
        session.name,
    ]
    os.execvp(command[0], command)


def cmd_tmux_wrapper(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    workdir = session.workdir if Path(session.workdir).is_dir() else str(Path.home())
    os.execvp("tmux", ["tmux", "new-session", "-A", "-s", session.tmux_session, "-c", workdir])


def cmd_serve_index(args: argparse.Namespace) -> None:
    serve_index(args.bind_host, args.port)


def cmd_stop(args: argparse.Namespace) -> None:
    validate_name(args.name)
    stop_session_service(args.name)


def cmd_kill(args: argparse.Namespace) -> None:
    validate_name(args.name)
    stop_session_service(args.name)
    if command_exists("tmux"):
        run(["tmux", "kill-session", "-t", args.name], check=False, quiet=True)


def cmd_doctor(args: argparse.Namespace) -> None:
    checks = {
        "python": True,
        "tmux": command_exists("tmux"),
        "ttyd": command_exists("ttyd"),
        "tailscale": command_exists("tailscale"),
        "codex": command_exists("codex"),
    }
    for name, ok in checks.items():
        print(f"{'ok' if ok else '!!'} {name}")
    print(f"platform: {platform.system()} {platform.release()}")
    print(f"config:   {config_dir()}")
    print(f"bind:     {default_bind_host()}")
    print(f"index:    http://{display_host()}:{args.index_port}/")
    if not checks["tailscale"]:
        print("warning: tailscale is optional but recommended for phone access without opening LAN ports")
    if platform.system().lower() == "windows":
        print("warning: Windows support is intended to run inside WSL2")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phonecodex")
    parser.add_argument("--version", action="version", version=f"phonecodex {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="install service files and mobile index asset")
    install.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    install.add_argument("--no-start", action="store_true")
    install.set_defaults(func=cmd_install)

    add = sub.add_parser("add", help="create and expose a tmux session")
    add.add_argument("name")
    add.add_argument("directory", nargs="?")
    add.add_argument("--codex", action="store_true", help="start codex in the tmux session")
    add.add_argument("--port", type=int)
    add.add_argument("--title")
    add.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    add.add_argument("--no-start", action="store_true")
    add.add_argument("--no-tmux", action="store_true")
    add.set_defaults(func=cmd_add)

    codex = sub.add_parser("codex", help="create and expose a tmux session that starts codex")
    codex.add_argument("name")
    codex.add_argument("directory", nargs="?")
    codex.add_argument("--port", type=int)
    codex.add_argument("--title")
    codex.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    codex.add_argument("--no-start", action="store_true")
    codex.add_argument("--no-tmux", action="store_true")
    codex.set_defaults(func=cmd_codex)

    expose = sub.add_parser("expose", help="expose an existing tmux session")
    expose.add_argument("name")
    expose.add_argument("directory", nargs="?")
    expose.add_argument("--port", type=int)
    expose.add_argument("--title")
    expose.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    expose.add_argument("--no-start", action="store_true")
    expose.add_argument("--no-tmux", action="store_true")
    expose.set_defaults(func=cmd_expose)

    list_cmd = sub.add_parser("list", help="list configured sessions")
    list_cmd.set_defaults(func=cmd_list)

    url = sub.add_parser("url", help="print a session URL")
    url.add_argument("name")
    url.set_defaults(func=cmd_url)

    attach = sub.add_parser("attach", help="attach to a configured tmux session")
    attach.add_argument("name")
    attach.set_defaults(func=cmd_attach)

    run_session = sub.add_parser("run-session", help="run one ttyd session; used by services")
    run_session.add_argument("name")
    run_session.add_argument("--bind-host")
    run_session.set_defaults(func=cmd_run_session)

    wrapper = sub.add_parser("tmux-wrapper", help="attach tmux; used by ttyd")
    wrapper.add_argument("name")
    wrapper.set_defaults(func=cmd_tmux_wrapper)

    serve = sub.add_parser("serve-index", help="run the index and toolbar API server")
    serve.add_argument("--bind-host")
    serve.add_argument("--port", type=int, default=DEFAULT_INDEX_PORT)
    serve.set_defaults(func=cmd_serve_index)

    stop = sub.add_parser("stop", help="stop a session service")
    stop.add_argument("name")
    stop.set_defaults(func=cmd_stop)

    kill = sub.add_parser("kill", help="stop service and kill tmux session")
    kill.add_argument("name")
    kill.set_defaults(func=cmd_kill)

    doctor = sub.add_parser("doctor", help="check required local tools")
    doctor.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0
