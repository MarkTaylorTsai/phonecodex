from __future__ import annotations

import argparse
import getpass
import importlib.resources
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .config import (
    DEFAULT_INDEX_PORT,
    DEPLOYMENT_MODES,
    SERVICE_PATH,
    SessionConfig,
    all_sessions,
    bind_host_for_mode,
    choose_port,
    choose_proxy_port,
    command_exists,
    command_path,
    config_dir,
    display_host,
    display_host_for_session,
    ensure_dirs,
    is_wsl,
    python_command,
    read_session,
    run_text,
    session_mobile_index_path,
    session_path,
    tailscale_dns_name,
    tailscale_ip,
    validate_name,
    write_session,
)
from .proxy import hash_password, serve_proxy
from .server import serve_index
from .toolbar import toolbar_js


def die(message: str) -> None:
    raise SystemExit(f"phonecodex: {message}")


def run(command: list[str], *, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    return subprocess.run(command, check=check, text=True, stdout=stdout, stderr=stderr)


def service_path() -> str:
    return os.environ.get("PHONECODEX_SERVICE_PATH", SERVICE_PATH)


def api_base_for_session(session: SessionConfig) -> str:
    if session.api_base == "origin" or session.proxy_enabled:
        return "location.origin"
    return f"location.protocol + '//' + location.hostname + ':{session.index_port}'"


def session_url(session: SessionConfig) -> str:
    if session.public_url:
        return session.public_url.rstrip("/")
    host = display_host_for_session(session)
    port = session.proxy_port if session.proxy_enabled else session.port
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}:{port}/"


def ensure_mobile_index(session: SessionConfig) -> Path:
    ensure_dirs()
    try:
        source = importlib.resources.files("phonecodex.assets").joinpath("mobile-index.html")
        html = source.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        html = "<!doctype html><html><body><pre>mobile-index.html asset is missing</pre></body></html>"

    html = re.sub(
        r"<script>\s*\(function\s*\(\)\s*\{(?:(?!</script>).)*mobile-toolbar\.js(?:(?!</script>).)*</script>\s*",
        "",
        html,
        flags=re.DOTALL,
    )
    inline_toolbar = (
        "<script>\n"
        f"window.PHONECODEX_SESSION_NAME = {json.dumps(session.name)};\n"
        f"window.PHONECODEX_API_BASE = {api_base_for_session(session)};\n"
        f"{toolbar_js(session.index_port)}\n"
        "</script>\n"
    )
    html = html.replace("</body>", inline_toolbar + "</body>")

    path = session_mobile_index_path(session.name)
    path.write_text(html, encoding="utf-8")
    return path


def unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def systemd_unit(name: str, exec_args: list[str]) -> str:
    quoted = " ".join(exec_args)
    return f"""[Unit]
Description={name}
After=default.target

[Service]
Type=simple
Environment=PATH={service_path()}
ExecStart={quoted}
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=default.target
"""


def install_systemd(index_port: int, bind_host: str, *, start_index: bool) -> None:
    ensure_dirs()
    unit_dir().mkdir(parents=True, exist_ok=True)
    python = python_command()
    (unit_dir() / "phonecodex@.service").write_text(
        systemd_unit(
            "PhoneCodex mobile terminal session (%i)",
            [python, "-m", "phonecodex", "run-session", "%i"],
        ),
        encoding="utf-8",
    )
    (unit_dir() / "phonecodex-proxy@.service").write_text(
        systemd_unit(
            "PhoneCodex authenticated terminal proxy (%i)",
            [python, "-m", "phonecodex", "run-proxy", "%i"],
        ),
        encoding="utf-8",
    )
    (unit_dir() / "phonecodex-index.service").write_text(
        systemd_unit(
            "PhoneCodex index and toolbar API",
            [python, "-m", "phonecodex", "serve-index", "--bind-host", bind_host, "--port", str(index_port)],
        ),
        encoding="utf-8",
    )
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
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{service_path()}</string>
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


def install_launchd(index_port: int, bind_host: str, *, start_index: bool) -> None:
    ensure_dirs()
    launch_agents_dir().mkdir(parents=True, exist_ok=True)
    path = launch_agents_dir() / "com.phonecodex.index.plist"
    path.write_text(
        plist(
            "com.phonecodex.index",
            [python_command(), "-m", "phonecodex", "serve-index", "--bind-host", bind_host, "--port", str(index_port)],
            "index",
        ),
        encoding="utf-8",
    )
    if start_index and command_exists("launchctl"):
        run(["launchctl", "unload", str(path)], check=False, quiet=True)
        run(["launchctl", "load", str(path)])


def install_services(index_port: int, mode: str, *, start_index: bool = True, bind_host: str = "") -> None:
    bind = bind_host or bind_host_for_mode(mode)
    system = platform.system().lower()
    if system == "linux":
        install_systemd(index_port, bind, start_index=start_index)
    elif system == "darwin":
        install_launchd(index_port, bind, start_index=start_index)
    elif system == "windows":
        print("Windows support is via WSL2. Run these commands inside WSL Ubuntu.")
    else:
        print("Unsupported service manager. Use phonecodex serve-index and phonecodex run-session manually.")


def start_index_service(index_port: int, mode: str, bind_host: str = "") -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        if not (unit_dir() / "phonecodex-index.service").exists():
            install_systemd(index_port, bind_host or bind_host_for_mode(mode), start_index=False)
        run(["systemctl", "--user", "enable", "--now", "phonecodex-index.service"])
    elif system == "darwin" and command_exists("launchctl"):
        if not (launch_agents_dir() / "com.phonecodex.index.plist").exists():
            install_launchd(index_port, bind_host or bind_host_for_mode(mode), start_index=False)
        run(["launchctl", "load", str(launch_agents_dir() / "com.phonecodex.index.plist")], check=False)


def start_session_service(session: SessionConfig) -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        if not (unit_dir() / "phonecodex@.service").exists():
            install_systemd(session.index_port, session.api_bind_host or bind_host_for_mode(session.mode), start_index=False)
        run(["systemctl", "--user", "enable", "--now", f"phonecodex@{session.name}.service"])
        if session.proxy_enabled:
            run(["systemctl", "--user", "enable", "--now", f"phonecodex-proxy@{session.name}.service"])
    elif system == "darwin" and command_exists("launchctl"):
        launch_agents_dir().mkdir(parents=True, exist_ok=True)
        for kind, args in {
            "session": [python_command(), "-m", "phonecodex", "run-session", session.name],
            "proxy": [python_command(), "-m", "phonecodex", "run-proxy", session.name],
        }.items():
            if kind == "proxy" and not session.proxy_enabled:
                continue
            label = f"com.phonecodex.{kind}.{session.name}"
            path = launch_agents_dir() / f"{label}.plist"
            path.write_text(plist(label, args, f"{kind}-{session.name}"), encoding="utf-8")
            run(["launchctl", "unload", str(path)], check=False, quiet=True)
            run(["launchctl", "load", str(path)])
    else:
        print(f"Run manually: phonecodex run-session {session.name}")
        if session.proxy_enabled:
            print(f"Run manually: phonecodex run-proxy {session.name}")


def stop_session_service(name: str) -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        run(["systemctl", "--user", "disable", "--now", f"phonecodex-proxy@{name}.service"], check=False, quiet=True)
        run(["systemctl", "--user", "disable", "--now", f"phonecodex@{name}.service"], check=False, quiet=True)
    elif system == "darwin" and command_exists("launchctl"):
        for kind in ("proxy", "session"):
            path = launch_agents_dir() / f"com.phonecodex.{kind}.{name}.plist"
            if path.exists():
                run(["launchctl", "unload", str(path)], check=False, quiet=True)


def service_action(action: str, name: str | None = None) -> None:
    system = platform.system().lower()
    if system == "linux" and command_exists("systemctl"):
        units = ["phonecodex-index.service"]
        if name:
            try:
                session = read_session(name)
                units.append(f"phonecodex@{name}.service")
                if session.proxy_enabled:
                    units.append(f"phonecodex-proxy@{name}.service")
            except SystemExit:
                units.extend([f"phonecodex@{name}.service", f"phonecodex-proxy@{name}.service"])
        elif action not in {"logs"}:
            units.extend(["phonecodex@*.service", "phonecodex-proxy@*.service"])
        if action == "logs":
            targets = [f"phonecodex@{name}.service"] if name else ["phonecodex-index.service"]
            if name:
                try:
                    session = read_session(name)
                    if session.proxy_enabled:
                        targets.append(f"phonecodex-proxy@{name}.service")
                except SystemExit:
                    pass
            for target in targets:
                run(["journalctl", "--user", "-u", target, "--no-pager", "-n", "120"], check=False)
            return
        for unit in units:
            run(["systemctl", "--user", action, unit], check=False)
        return
    if system == "darwin":
        print("Use launchctl list | grep phonecodex and logs under ~/.config/phonecodex/logs")
        return
    print("No native service manager available; use foreground commands.")


def ensure_tmux_session(name: str, workdir: Path, initial_command: str = "") -> None:
    if not command_exists("tmux"):
        die("tmux command not found")
    exists = subprocess.run(["tmux", "has-session", "-t", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if exists.returncode == 0:
        return
    run(["tmux", "new-session", "-d", "-s", name, "-c", str(workdir)])
    if initial_command:
        run(["tmux", "send-keys", "-t", f"{name}:0.0", initial_command, "C-m"])


def read_password(args: argparse.Namespace, mode: str, proxy_enabled: bool) -> tuple[str, str, str]:
    username = args.auth_user or ""
    password = args.auth_password or ""
    generated = ""
    if proxy_enabled and mode == "cloudflare":
        username = username or "phonecodex"
        if not password:
            generated = secrets.token_urlsafe(18)
            password = generated
    if username and not password:
        password = getpass.getpass("PhoneCodex proxy password: ")
    return username, hash_password(password) if password else "", generated


def create_session(args: argparse.Namespace, *, codex: bool = False, expose: bool = False) -> None:
    name = args.name
    validate_name(name)
    existing = read_session(name) if session_path(name).exists() else None

    mode = args.mode
    if mode not in DEPLOYMENT_MODES:
        die(f"--mode must be one of: {', '.join(sorted(DEPLOYMENT_MODES))}")

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

    proxy_enabled = bool(args.proxy or mode == "cloudflare")
    ttyd_bind = args.ttyd_bind_host or ("127.0.0.1" if proxy_enabled else bind_host_for_mode(mode))
    api_bind = args.api_bind_host or ("127.0.0.1" if proxy_enabled else bind_host_for_mode(mode))
    proxy_bind = args.proxy_bind_host or "127.0.0.1"
    port = args.port or choose_port(existing, ttyd_bind)
    proxy_port = args.proxy_port or (choose_proxy_port(existing, proxy_bind) if proxy_enabled else 0)
    auth_user, auth_hash, generated_password = read_password(args, mode, proxy_enabled)
    title = args.title or (f"{name} codex" if codex else name)
    public_url = args.public_url or (f"https://{args.cloudflare_hostname}" if args.cloudflare_hostname else "")
    session = SessionConfig(
        name=name,
        port=int(port),
        title=title,
        tmux_session=name,
        workdir=str(workdir),
        index_port=args.index_port,
        mode=mode,
        ttyd_bind_host=ttyd_bind,
        api_bind_host=api_bind,
        proxy_enabled=proxy_enabled,
        proxy_port=int(proxy_port or 0),
        proxy_bind_host=proxy_bind,
        api_base="origin" if proxy_enabled else "index",
        public_url=public_url,
        auth_username=auth_user,
        auth_password_hash=auth_hash,
        cloudflare_tunnel=args.cloudflare_tunnel or "",
        cloudflare_hostname=args.cloudflare_hostname or "",
        cloudflare_config=args.cloudflare_config or "",
    )
    write_session(session)
    ensure_mobile_index(session)

    if not args.no_tmux:
        ensure_tmux_session(name, workdir, "codex" if codex else "")

    if not args.no_start:
        start_index_service(session.index_port, session.mode, session.api_bind_host)
        start_session_service(session)

    print(f"{session.name}  {session_url(session)}  {session.workdir}")
    if generated_password:
        print(f"generated proxy auth: {auth_user}:{generated_password}")


def cmd_install(args: argparse.Namespace) -> None:
    install_services(args.index_port, args.mode, start_index=not args.no_start, bind_host=args.bind_host or "")
    print(f"config: {config_dir()}")
    print(f"index:  http://{args.bind_host or bind_host_for_mode(args.mode)}:{args.index_port}/")


def cmd_add(args: argparse.Namespace) -> None:
    create_session(args, codex=args.codex)


def cmd_codex(args: argparse.Namespace) -> None:
    create_session(args, codex=True)


def cmd_expose(args: argparse.Namespace) -> None:
    create_session(args, expose=True)


def cmd_list(args: argparse.Namespace) -> None:
    print(f"{'NAME':18} {'MODE':10} {'TTYD':6} {'PROXY':6} {'URL':42} DIR")
    for session in all_sessions():
        print(
            f"{session.name:18} {session.mode:10} {session.port:<6} "
            f"{(session.proxy_port or '-'):6} {session_url(session):42} {session.workdir}"
        )


def cmd_url(args: argparse.Namespace) -> None:
    print(session_url(read_session(args.name)))


def cmd_verify(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    index = ensure_mobile_index(session)
    index_html = index.read_text(encoding="utf-8", errors="replace")
    toolbar = toolbar_js(session.index_port)
    checks = [
        ("session config", True, str(session_path(session.name))),
        ("generated mobile index", index.exists(), str(index)),
        ("index contains inline toolbar", "pcx-toolbar" in index_html and "pcx-paste-ask" in index_html, str(index)),
        ("index pins session name", session.name in index_html, session.name),
        ("toolbar has Paste/Insert/Ask", all(token in toolbar for token in ["Paste", "Insert", "Ask"]), ""),
        ("toolbar has arrow keys", all(token in toolbar for token in ['sendKey("up")', 'sendKey("down")', 'sendKey("left")', 'sendKey("right")']), ""),
    ]
    if session.proxy_enabled:
        checks.append(("proxy configured", bool(session.proxy_port), str(session.proxy_port)))
        checks.append(("proxy API base is origin", "location.origin" in index_html, "location.origin"))
    if not args.skip_network:
        urls = [(session_url(session), "running page contains toolbar")]
        api_url = session_url(session).rstrip("/") + "/mobile-toolbar.js" if session.proxy_enabled else f"http://{display_host()}:{session.index_port}/mobile-toolbar.js"
        urls.append((api_url, "toolbar API endpoint serves buttons"))
        for url, label in urls:
            try:
                request = urllib.request.Request(url)
                if session.auth_username and args.auth_password:
                    import base64

                    raw = f"{session.auth_username}:{args.auth_password}".encode("utf-8")
                    request.add_header("Authorization", "Basic " + base64.b64encode(raw).decode("ascii"))
                with urllib.request.urlopen(request, timeout=2) as response:
                    page = response.read(2_000_000).decode("utf-8", errors="replace")
                checks.append((label, "pcx-toolbar" in page, url))
            except (OSError, urllib.error.URLError) as error:
                detail = f"{url} ({error})"
                if session.auth_username and not args.auth_password:
                    detail += " - pass --auth-password for authenticated proxies"
                checks.append((label.replace("contains", "reachable"), False, detail))
    for label, ok, detail in checks:
        print(f"{'ok' if ok else '!!'} {label}{(': ' + detail) if detail else ''}")
    print(f"session URL: {session_url(session)}")
    if platform.system().lower() == "linux" and command_exists("systemctl"):
        for unit in [f"phonecodex@{session.name}.service", f"phonecodex-proxy@{session.name}.service"]:
            status = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ).stdout.strip()
            print(f"{unit}: {status or 'unknown'}")
    if not all(ok for _, ok, _ in checks):
        raise SystemExit(1)


def cmd_attach(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    os.execvp("tmux", ["tmux", "new-session", "-A", "-s", session.tmux_session, "-c", session.workdir])


def cmd_run_session(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    if not command_exists("ttyd"):
        die("ttyd command not found")
    index = ensure_mobile_index(session)
    bind_host = args.bind_host or session.ttyd_bind_host or bind_host_for_mode(session.mode)
    command = [
        "ttyd",
        "--interface",
        bind_host,
        "--port",
        str(session.port),
        "--index",
        str(index),
        "--writable",
    ]
    if not session.proxy_enabled:
        command.append("--check-origin")
    command.extend(
        [
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
    )
    os.execvp(command[0], command)


def cmd_run_proxy(args: argparse.Namespace) -> None:
    serve_proxy(args.name, args.bind_host, args.port)


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
    commands = ["tmux", "ttyd", "tailscale", "cloudflared", "codex"]
    print(f"platform: {platform.system()} {platform.release()}{' (WSL2)' if is_wsl() else ''}")
    print(f"python:   {sys.version.split()[0]}")
    print(f"config:   {config_dir()}")
    print(f"service PATH: {service_path()}")
    for command in commands:
        interactive = command_path(command) or "-"
        service = command_path(command, service_path()) or "-"
        marker = "ok" if interactive != "-" else "!!"
        print(f"{marker} {command:11} interactive={interactive} service={service}")
        if interactive != "-" and service == "-":
            print(f"warning: {command} is visible now but not in service PATH")
    if command_exists("tailscale"):
        print(f"tailscale ip:       {tailscale_ip() or '-'}")
        print(f"tailscale MagicDNS: {tailscale_dns_name() or '-'}")
        print(f"tailscale status:   {run_text(['tailscale', 'status', '--self', '--peers=false'], timeout=8) or '-'}")
        serve_status = run_text(["tailscale", "serve", "status"], timeout=8)
        print(f"tailscale serve:    {serve_status or '-'}")
    if command_exists("cloudflared"):
        print(f"cloudflared:        {run_text(['cloudflared', '--version'], timeout=5) or '-'}")
    if platform.system().lower() == "linux" and command_exists("systemctl"):
        print(f"systemd user:       {run_text(['systemctl', '--user', 'is-system-running'], timeout=5) or '-'}")
        if is_wsl():
            print("WSL2: systemd user services require WSL systemd=true; otherwise use foreground commands.")
    if platform.system().lower() == "windows":
        print("warning: native Windows is limited; WSL2 is the supported path.")


def patch_cloudflared_config(path: Path, hostname: str, service_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rule = f"  - hostname: {hostname}\n    service: {service_url}\n"
    if f"hostname: {hostname}" in existing:
        lines = existing.splitlines()
        output: list[str] = []
        skip_next = False
        for idx, line in enumerate(lines):
            if skip_next:
                output.append(f"    service: {service_url}")
                skip_next = False
                continue
            output.append(line)
            if line.strip() == f"hostname: {hostname}":
                skip_next = idx + 1 < len(lines) and lines[idx + 1].strip().startswith("service:")
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
        return
    if "ingress:" not in existing:
        existing = existing.rstrip() + "\ningress:\n"
    fallback = "  - service: http_status:404"
    if fallback in existing:
        existing = existing.replace(fallback, rule + fallback)
    else:
        existing = existing.rstrip() + "\n" + rule + fallback + "\n"
    path.write_text(existing, encoding="utf-8")


def cmd_deploy(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    if args.kind == "local":
        proxy_port = choose_proxy_port(session, "127.0.0.1") if args.proxy else 0
        session = SessionConfig(
            **{
                **session.__dict__,
                "mode": "local",
                "ttyd_bind_host": "127.0.0.1",
                "api_bind_host": "127.0.0.1",
                "proxy_enabled": bool(args.proxy),
                "proxy_port": proxy_port,
                "proxy_bind_host": "127.0.0.1",
                "api_base": "origin" if args.proxy else "index",
                "public_url": "",
            }
        )
        write_session(session)
        ensure_mobile_index(session)
        print(session_url(session))
        return
    if args.kind == "tailscale":
        dns_name = tailscale_dns_name()
        ip_addr = tailscale_ip()
        if args.serve:
            if not command_exists("tailscale"):
                die("tailscale command not found")
            proxy_port = session.proxy_port or choose_proxy_port(session, "127.0.0.1")
            session = SessionConfig(
                **{
                    **session.__dict__,
                    "mode": "tailscale",
                    "ttyd_bind_host": "127.0.0.1",
                    "api_bind_host": "127.0.0.1",
                    "proxy_enabled": True,
                    "proxy_port": proxy_port,
                    "proxy_bind_host": "127.0.0.1",
                    "api_base": "origin",
                    "public_url": f"https://{dns_name}" if dns_name else "",
                }
            )
            write_session(session)
            ensure_mobile_index(session)
            run(["tailscale", "serve", "--bg", "--yes", f"http://127.0.0.1:{proxy_port}"], check=False)
        else:
            bind = ip_addr or "127.0.0.1"
            session = SessionConfig(
                **{
                    **session.__dict__,
                    "mode": "tailscale",
                    "ttyd_bind_host": bind,
                    "api_bind_host": bind,
                    "proxy_enabled": False,
                    "proxy_port": 0,
                    "proxy_bind_host": "127.0.0.1",
                    "api_base": "index",
                    "public_url": "",
                }
            )
            write_session(session)
            ensure_mobile_index(session)
        print(f"tailscale ip: {tailscale_ip() or '-'}")
        print(f"MagicDNS:     {tailscale_dns_name() or '-'}")
        print(f"session URL:  {session_url(session)}")
        if args.serve:
            print(f"serve target: http://127.0.0.1:{session.proxy_port}")
        return
    if args.kind == "cloudflare":
        if not args.hostname or not args.tunnel:
            die("cloudflare deployment requires --hostname and --tunnel")
        proxy_port = session.proxy_port or choose_proxy_port(session, "127.0.0.1")
        auth_user = session.auth_username or "phonecodex"
        auth_hash = session.auth_password_hash
        generated_password = ""
        if not auth_hash:
            generated_password = secrets.token_urlsafe(18)
            auth_hash = hash_password(generated_password)
        session = SessionConfig(
            **{
                **session.__dict__,
                "mode": "cloudflare",
                "ttyd_bind_host": "127.0.0.1",
                "api_bind_host": "127.0.0.1",
                "proxy_enabled": True,
                "proxy_port": proxy_port,
                "proxy_bind_host": "127.0.0.1",
                "api_base": "origin",
                "public_url": f"https://{args.hostname}",
                "auth_username": auth_user,
                "auth_password_hash": auth_hash,
                "cloudflare_tunnel": args.tunnel,
                "cloudflare_hostname": args.hostname,
                "cloudflare_config": str(args.config),
            }
        )
        write_session(session)
        ensure_mobile_index(session)
        patch_cloudflared_config(Path(args.config).expanduser(), args.hostname, f"http://127.0.0.1:{proxy_port}")
        if args.route_dns:
            run(["cloudflared", "tunnel", "route", "dns", args.tunnel, args.hostname], check=False)
        print(f"cloudflare hostname: https://{args.hostname}")
        print(f"cloudflared config:  {Path(args.config).expanduser()}")
        if generated_password:
            print(f"generated proxy auth: {auth_user}:{generated_password}")


def cmd_service(args: argparse.Namespace) -> None:
    if args.action == "install":
        cmd_install(args)
        return
    if args.name and args.action in {"start", "restart"}:
        session = read_session(args.name)
        if args.action == "restart":
            stop_session_service(args.name)
        start_index_service(session.index_port, session.mode, session.api_bind_host)
        start_session_service(session)
        return
    if args.name and args.action == "stop":
        stop_session_service(args.name)
        return
    service_action(args.action, args.name)


def add_session_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name")
    parser.add_argument("directory", nargs="?")
    parser.add_argument("--mode", choices=sorted(DEPLOYMENT_MODES), default="tailscale")
    parser.add_argument("--proxy", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--proxy-port", type=int)
    parser.add_argument("--title")
    parser.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    parser.add_argument("--ttyd-bind-host")
    parser.add_argument("--api-bind-host")
    parser.add_argument("--proxy-bind-host")
    parser.add_argument("--public-url")
    parser.add_argument("--auth-user")
    parser.add_argument("--auth-password")
    parser.add_argument("--cloudflare-tunnel")
    parser.add_argument("--cloudflare-hostname")
    parser.add_argument("--cloudflare-config")
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--no-tmux", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phonecodex")
    parser.add_argument("--version", action="version", version=f"phonecodex {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="install service files and mobile index asset")
    install.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    install.add_argument("--mode", choices=sorted(DEPLOYMENT_MODES), default="tailscale")
    install.add_argument("--bind-host")
    install.add_argument("--no-start", action="store_true")
    install.set_defaults(func=cmd_install)

    add = sub.add_parser("add", help="create and expose a tmux session")
    add_session_options(add)
    add.add_argument("--codex", action="store_true", help="start codex in the tmux session")
    add.set_defaults(func=cmd_add)

    codex = sub.add_parser("codex", help="create and expose a tmux session that starts codex")
    add_session_options(codex)
    codex.set_defaults(func=cmd_codex)

    expose = sub.add_parser("expose", help="expose an existing tmux session")
    add_session_options(expose)
    expose.set_defaults(func=cmd_expose)

    list_cmd = sub.add_parser("list", help="list configured sessions")
    list_cmd.set_defaults(func=cmd_list)

    url = sub.add_parser("url", help="print a session URL")
    url.add_argument("name")
    url.set_defaults(func=cmd_url)

    verify = sub.add_parser("verify", help="verify toolbar/index/proxy generation for a session")
    verify.add_argument("name")
    verify.add_argument("--skip-network", action="store_true")
    verify.add_argument("--auth-password", help="password for authenticated proxy network checks")
    verify.set_defaults(func=cmd_verify)

    attach = sub.add_parser("attach", help="attach to a configured tmux session")
    attach.add_argument("name")
    attach.set_defaults(func=cmd_attach)

    run_session = sub.add_parser("run-session", help="run one ttyd session; used by services")
    run_session.add_argument("name")
    run_session.add_argument("--bind-host")
    run_session.set_defaults(func=cmd_run_session)

    run_proxy = sub.add_parser("run-proxy", help="run one authenticated reverse proxy; used by services")
    run_proxy.add_argument("name")
    run_proxy.add_argument("--bind-host")
    run_proxy.add_argument("--port", type=int)
    run_proxy.set_defaults(func=cmd_run_proxy)

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

    doctor = sub.add_parser("doctor", help="check required local tools and deployment state")
    doctor.set_defaults(func=cmd_doctor)

    service = sub.add_parser("service", help="install/start/stop/restart/status/logs native services")
    service.add_argument("action", choices=["install", "start", "stop", "restart", "status", "logs"])
    service.add_argument("name", nargs="?")
    service.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    service.add_argument("--mode", choices=sorted(DEPLOYMENT_MODES), default="tailscale")
    service.add_argument("--bind-host")
    service.add_argument("--no-start", action="store_true")
    service.set_defaults(func=cmd_service)

    deploy = sub.add_parser("deploy", help="configure local, tailscale, or cloudflare deployment")
    deploy_sub = deploy.add_subparsers(dest="kind", required=True)
    local = deploy_sub.add_parser("local")
    local.add_argument("name")
    local.add_argument("--proxy", action="store_true")
    local.set_defaults(func=cmd_deploy)
    tailscale = deploy_sub.add_parser("tailscale")
    tailscale.add_argument("name")
    tailscale.add_argument("--serve", action="store_true")
    tailscale.set_defaults(func=cmd_deploy)
    cloudflare = deploy_sub.add_parser("cloudflare")
    cloudflare.add_argument("name")
    cloudflare.add_argument("--hostname", required=True)
    cloudflare.add_argument("--tunnel", required=True)
    cloudflare.add_argument("--config", default=str(Path.home() / ".cloudflared" / "config.yml"))
    cloudflare.add_argument("--route-dns", action="store_true")
    cloudflare.set_defaults(func=cmd_deploy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0
