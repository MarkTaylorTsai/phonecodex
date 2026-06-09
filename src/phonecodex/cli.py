from __future__ import annotations

import argparse
import getpass
import importlib.resources
import json
import os
import platform
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
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
    ensure_env_file,
    env_file_path,
    is_wsl,
    parse_env_file,
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
from .deploy import hostname_for_session, multi_session_name, patch_cloudflared_config
from .proxy import hash_password, serve_proxy
from .server import serve_index
from .services import launchd_plist_text, systemd_unit_text
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
    return systemd_unit_text(name, exec_args, service_path(), env_file_path())


def install_systemd(index_port: int, bind_host: str, *, start_index: bool) -> None:
    ensure_dirs()
    ensure_env_file()
    unit_dir().mkdir(parents=True, exist_ok=True)
    python = python_command()
    session_text = systemd_unit(
        "PhoneCodex mobile terminal session (%i)",
        [python, "-m", "phonecodex", "run-session", "%i"],
    )
    (unit_dir() / "phonecodex@.service").write_text(
        session_text,
        encoding="utf-8",
    )
    (unit_dir() / "phonecodex-session@.service").write_text(session_text, encoding="utf-8")
    (unit_dir() / "phonecodex-proxy@.service").write_text(
        systemd_unit(
            "PhoneCodex authenticated terminal proxy (%i)",
            [python, "-m", "phonecodex", "run-proxy", "%i"],
        ),
        encoding="utf-8",
    )
    api_text = systemd_unit(
        "PhoneCodex index and toolbar API",
        [python, "-m", "phonecodex", "serve-index", "--bind-host", bind_host, "--port", str(index_port)],
    )
    (unit_dir() / "phonecodex-index.service").write_text(api_text, encoding="utf-8")
    (unit_dir() / "phonecodex-api.service").write_text(api_text, encoding="utf-8")
    if command_exists("systemctl"):
        run(["systemctl", "--user", "daemon-reload"])
        if start_index:
            run(["systemctl", "--user", "enable", "--now", "phonecodex-index.service"])


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist(label: str, args: list[str], log_name: str) -> str:
    log_dir = config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return launchd_plist_text(label, args, log_name, log_dir, service_path(), env_file_path())


def install_launchd(index_port: int, bind_host: str, *, start_index: bool) -> None:
    ensure_dirs()
    ensure_env_file()
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


def password_from_args(args: argparse.Namespace) -> str:
    password = getattr(args, "auth_password", "") or ""
    password_env = getattr(args, "auth_password_env", "") or ""
    if password_env:
        password = os.environ.get(password_env, "")
        if not password:
            die(f"environment variable is empty or missing: {password_env}")
    return password


def read_password(args: argparse.Namespace, mode: str, proxy_enabled: bool) -> tuple[str, str, str]:
    if not proxy_enabled:
        return "", "", ""
    env_values = parse_env_file()
    username = args.auth_user or env_values.get("PHONECODEX_AUTH_USER", "")
    password = password_from_args(args) or env_values.get("PHONECODEX_AUTH_PASSWORD", "")
    generated = ""
    if proxy_enabled and mode == "cloudflare":
        username = username or "phonecodex"
        if not password:
            generated = secrets.token_urlsafe(18)
            password = generated
    if username and not password:
        password = getpass.getpass("PhoneCodex proxy password: ")
    return username, hash_password(password) if password else "", generated


def configure_proxy_auth(
    session: SessionConfig,
    args: argparse.Namespace,
    *,
    default_username: str = "phonecodex",
    generate_if_missing: bool = False,
) -> tuple[str, str, str]:
    env_values = parse_env_file()
    username = args.auth_user or session.auth_username or env_values.get("PHONECODEX_AUTH_USER", "") or default_username
    password = password_from_args(args) or env_values.get("PHONECODEX_AUTH_PASSWORD", "")
    generated = ""
    if not password and not session.auth_password_hash and generate_if_missing:
        generated = secrets.token_urlsafe(18)
        password = generated
    password_hash = hash_password(password) if password else session.auth_password_hash
    return username, password_hash, generated


def maybe_write_generated_env(username: str, password: str) -> None:
    if not password:
        return
    path = env_file_path()
    existing_password = parse_env_file().get("PHONECODEX_AUTH_PASSWORD", "")
    if existing_password:
        print(f"generated proxy auth kept in session hash; env file already has a password: {path}")
        return
    ensure_dirs()
    path.write_text(
        f"PHONECODEX_AUTH_USER={username}\nPHONECODEX_AUTH_PASSWORD={password}\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        os.chmod(path, 0o600)
    print(f"generated proxy auth written to {path}")
    print("store this password now; the env file is chmod 600")


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


def basic_auth_header(username: str, password: str) -> str:
    import base64

    raw = f"{username}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request_text(url: str, *, password: str = "", username: str = "phonecodex", data: dict[str, object] | None = None) -> tuple[int, str]:
    body = None
    request = urllib.request.Request(url)
    if password:
        request.add_header("Authorization", basic_auth_header(username, password))
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, data=body, timeout=3) as response:
            return response.status, response.read(2_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(2_000_000).decode("utf-8", errors="replace")


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, timeout: float = 8) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def print_checks(checks: list[tuple[str, bool, str]]) -> None:
    for label, ok, detail in checks:
        print(f"{'ok' if ok else '!!'} {label}{(': ' + detail) if detail else ''}")
    if not all(ok for _, ok, _ in checks):
        raise SystemExit(1)


def cmd_verify_local_test(args: argparse.Namespace) -> None:
    checks: list[tuple[str, bool, str]] = [
        ("python package import", True, "phonecodex"),
        ("tmux exists", command_exists("tmux"), command_path("tmux") or "-"),
        ("ttyd exists", command_exists("ttyd"), command_path("ttyd") or "-"),
    ]
    if not all(ok for _, ok, _ in checks):
        print_checks(checks)
        return

    password = "phonecodex-local-test"
    name = "phonecodex-local-test"
    processes: list[subprocess.Popen[bytes]] = []
    old_config = os.environ.get("PHONECODEX_CONFIG_DIR")
    with tempfile.TemporaryDirectory(prefix="phonecodex-local-test-") as temp:
        os.environ["PHONECODEX_CONFIG_DIR"] = temp
        env = os.environ.copy()
        port = free_tcp_port()
        proxy_port = free_tcp_port()
        index_port = free_tcp_port()
        try:
            create = [
                sys.executable,
                "-m",
                "phonecodex",
                "add",
                name,
                temp,
                "--mode",
                "local",
                "--proxy",
                "--auth-user",
                "phonecodex",
                "--auth-password",
                password,
                "--port",
                str(port),
                "--proxy-port",
                str(proxy_port),
                "--index-port",
                str(index_port),
                "--no-start",
                "--no-tmux",
            ]
            subprocess.run(create, check=True, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            subprocess.run(["tmux", "new-session", "-d", "-s", name, "-c", temp], check=True)
            checks.append(("tmux session exists", True, name))

            for command in [
                [sys.executable, "-m", "phonecodex", "serve-index", "--bind-host", "127.0.0.1", "--port", str(index_port)],
                [sys.executable, "-m", "phonecodex", "run-session", name],
                [sys.executable, "-m", "phonecodex", "run-proxy", name],
            ]:
                processes.append(subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env))

            checks.append(("API port listening", wait_for_port(index_port), str(index_port)))
            checks.append(("ttyd port listening", wait_for_port(port), str(port)))
            checks.append(("proxy port listening", wait_for_port(proxy_port), str(proxy_port)))

            base = f"http://127.0.0.1:{proxy_port}"
            status, _ = request_text(base + "/")
            checks.append(("no-auth proxy returns 401", status == 401, str(status)))
            status, html = request_text(base + "/", username="phonecodex", password=password)
            checks.append(("with-auth proxy returns 200", status == 200, str(status)))
            checks.append(("HTML includes toolbar", "pcx-toolbar" in html and "pcx-paste-ask" in html, base + "/"))
            checks.append(("HTML API base is location.origin", "window.PHONECODEX_API_BASE = location.origin" in html, base + "/"))

            status, body = request_text(base + "/api/session?port=443", username="phonecodex", password=password)
            session_payload = json.loads(body) if status == 200 else {}
            checks.append(("api session maps public port", session_payload.get("name") == name, body[:200]))

            status, body = request_text(
                base + "/api/key",
                username="phonecodex",
                password=password,
                data={"session": name, "key": "tab"},
            )
            checks.append(("api key returns ok", status == 200 and '"ok": true' in body, body[:200]))

            marker = "PHONECODEX_LOCAL_TEST_MARKER"
            status, body = request_text(
                base + "/api/paste",
                username="phonecodex",
                password=password,
                data={"session": name, "text": marker, "submit": False},
            )
            time.sleep(0.3)
            capture = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", name],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ).stdout
            checks.append(("api paste returns ok", status == 200 and '"ok": true' in body, body[:200]))
            checks.append(("paste appears in tmux capture", marker in capture, marker))
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
            subprocess.run(["tmux", "kill-session", "-t", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if old_config is None:
                os.environ.pop("PHONECODEX_CONFIG_DIR", None)
            else:
                os.environ["PHONECODEX_CONFIG_DIR"] = old_config
    print_checks(checks)


def cmd_verify(args: argparse.Namespace) -> None:
    if getattr(args, "local_test", False):
        cmd_verify_local_test(args)
        return
    if not args.name:
        die("verify requires NAME unless --local-test is used")
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
                    request.add_header("Authorization", basic_auth_header(session.auth_username, args.auth_password))
                with urllib.request.urlopen(request, timeout=2) as response:
                    page = response.read(2_000_000).decode("utf-8", errors="replace")
                checks.append((label, "pcx-toolbar" in page, url))
            except (OSError, urllib.error.URLError) as error:
                detail = f"{url} ({error})"
                if session.auth_username and not args.auth_password:
                    detail += " - pass --auth-password for authenticated proxies"
                checks.append((label.replace("contains", "reachable"), False, detail))
    print_checks(checks)
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


def update_proxy_session(
    session: SessionConfig,
    args: argparse.Namespace,
    *,
    proxy_port: int | None = None,
    proxy_bind_host: str = "127.0.0.1",
    generate_auth: bool = False,
) -> SessionConfig:
    selected_proxy_port = proxy_port or getattr(args, "proxy_port", None) or session.proxy_port or choose_proxy_port(session, proxy_bind_host)
    auth_user, auth_hash, generated_password = configure_proxy_auth(session, args, generate_if_missing=generate_auth)
    updated = SessionConfig(
        **{
            **session.__dict__,
            "proxy_enabled": True,
            "proxy_port": int(selected_proxy_port),
            "proxy_bind_host": proxy_bind_host,
            "ttyd_bind_host": "127.0.0.1",
            "api_bind_host": "127.0.0.1",
            "api_base": "origin",
            "auth_username": auth_user,
            "auth_password_hash": auth_hash,
        }
    )
    write_session(updated)
    ensure_mobile_index(updated)
    if generated_password:
        maybe_write_generated_env(auth_user, generated_password)
    return updated


def cmd_proxy_run(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    if args.proxy_port or args.auth_user or args.auth_password or args.auth_password_env:
        session = update_proxy_session(session, args, proxy_bind_host=args.bind_host or session.proxy_bind_host or "127.0.0.1")
    serve_proxy(session.name, args.bind_host, args.proxy_port)


def cmd_proxy_install_service(args: argparse.Namespace) -> None:
    session = read_session(args.name)
    session = update_proxy_session(session, args, generate_auth=bool(args.generate_auth))
    start_index_service(session.index_port, session.mode, session.api_bind_host)
    start_session_service(session)
    print(f"proxy service: {session.name} http://{session.proxy_bind_host}:{session.proxy_port}/")


def cmd_proxy_verify(args: argparse.Namespace) -> None:
    args.skip_network = bool(args.skip_network)
    cmd_verify(args)


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


def cmd_auth(args: argparse.Namespace) -> None:
    if args.auth_command != "init":
        die("unsupported auth command")
    path = env_file_path()
    if path.exists() and not args.force:
        print(f"env file already exists: {path}")
        print("use --force to overwrite it")
        return
    password = password_from_args(args)
    generated = ""
    if args.generate and not password:
        generated = secrets.token_urlsafe(18)
        password = generated
    if args.force and path.exists():
        path.unlink()
    path = ensure_env_file(args.user, password)
    print(f"env file: {path}")
    print("permissions: 600")
    if generated:
        print(f"generated proxy auth: {args.user}:{generated}")


def cmd_deploy(args: argparse.Namespace) -> None:
    if args.kind == "cloudflare" and (getattr(args, "count", 1) > 1 or getattr(args, "name", "") == "multi"):
        cmd_deploy_cloudflare_multi(args)
        return
    session = read_session(args.name)
    if args.kind == "local":
        proxy_enabled = bool(args.proxy or getattr(args, "proxy_port", None))
        proxy_port = args.proxy_port or (choose_proxy_port(session, "127.0.0.1") if proxy_enabled else 0)
        auth_user, auth_hash, generated_password = configure_proxy_auth(session, args, generate_if_missing=proxy_enabled and bool(args.generate_auth))
        session = SessionConfig(
            **{
                **session.__dict__,
                "mode": "local",
                "ttyd_bind_host": "127.0.0.1",
                "api_bind_host": "127.0.0.1",
                "proxy_enabled": proxy_enabled,
                "proxy_port": proxy_port,
                "proxy_bind_host": "127.0.0.1",
                "api_base": "origin" if proxy_enabled else "index",
                "public_url": "",
                "auth_username": auth_user if proxy_enabled else session.auth_username,
                "auth_password_hash": auth_hash if proxy_enabled else session.auth_password_hash,
            }
        )
        write_session(session)
        ensure_mobile_index(session)
        if generated_password:
            maybe_write_generated_env(auth_user, generated_password)
        print(session_url(session))
        return
    if args.kind == "tailscale":
        dns_name = args.hostname or tailscale_dns_name()
        ip_addr = tailscale_ip()
        wants_proxy = bool(args.serve or args.proxy_port or args.auth_user or args.auth_password or args.auth_password_env)
        if args.serve or wants_proxy:
            if not command_exists("tailscale"):
                die("tailscale command not found")
            proxy_bind = "127.0.0.1" if args.serve else (ip_addr or "127.0.0.1")
            proxy_port = args.proxy_port or session.proxy_port or choose_proxy_port(session, proxy_bind)
            auth_user, auth_hash, generated_password = configure_proxy_auth(
                session,
                args,
                generate_if_missing=bool(args.generate_auth),
            )
            public_url = ""
            if args.serve and dns_name:
                public_url = f"https://{dns_name}"
            elif dns_name:
                public_url = f"http://{dns_name}:{proxy_port}/"
            session = SessionConfig(
                **{
                    **session.__dict__,
                    "mode": "tailscale",
                    "ttyd_bind_host": "127.0.0.1",
                    "api_bind_host": "127.0.0.1",
                    "proxy_enabled": True,
                    "proxy_port": proxy_port,
                    "proxy_bind_host": proxy_bind,
                    "api_base": "origin",
                    "public_url": public_url,
                    "auth_username": auth_user,
                    "auth_password_hash": auth_hash,
                }
            )
            write_session(session)
            ensure_mobile_index(session)
            if generated_password:
                maybe_write_generated_env(auth_user, generated_password)
            if args.serve:
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
        proxy_port = args.proxy_port or session.proxy_port or choose_proxy_port(session, "127.0.0.1")
        auth_user, auth_hash, generated_password = configure_proxy_auth(session, args, generate_if_missing=True)
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
            maybe_write_generated_env(auth_user, generated_password)
        print("restart cloudflared with: cloudflared tunnel run " + args.tunnel)


def cmd_deploy_cloudflare_multi(args: argparse.Namespace) -> None:
    if not args.tunnel:
        die("cloudflare multi deployment requires --tunnel")
    if not args.base_hostname and not args.host_pattern:
        die("cloudflare multi deployment requires --base-hostname or --host-pattern")
    workdir = Path(args.directory or os.getcwd()).expanduser().resolve()
    if not workdir.is_dir():
        die(f"directory does not exist: {workdir}")
    if args.codex and not command_exists("codex"):
        die("codex command not found in PATH")
    count = int(args.count)
    if count < 1:
        die("--count must be at least 1")
    config_path = Path(args.config).expanduser()
    sessions: list[SessionConfig] = []
    for idx in range(1, count + 1):
        name = multi_session_name(args.session_prefix, idx)
        hostname = hostname_for_session(args.host_pattern or "", args.base_hostname or "", idx)
        existing = read_session(name) if session_path(name).exists() else None
        port = (args.start_port + idx - 1) if args.start_port else choose_port(existing, "127.0.0.1")
        proxy_port = (args.start_proxy_port + idx - 1) if args.start_proxy_port else choose_proxy_port(existing, "127.0.0.1")
        auth_user, auth_hash, generated_password = configure_proxy_auth(
            existing
            or SessionConfig(
                name=name,
                port=port,
                title=f"{name} codex" if args.codex else name,
                tmux_session=name,
                workdir=str(workdir),
                index_port=args.index_port,
            ),
            args,
            generate_if_missing=True,
        )
        if generated_password:
            maybe_write_generated_env(auth_user, generated_password)
        session = SessionConfig(
            name=name,
            port=port,
            title=f"{name} codex" if args.codex else name,
            tmux_session=name,
            workdir=str(workdir),
            index_port=args.index_port,
            mode="cloudflare",
            ttyd_bind_host="127.0.0.1",
            api_bind_host="127.0.0.1",
            proxy_enabled=True,
            proxy_port=proxy_port,
            proxy_bind_host="127.0.0.1",
            api_base="origin",
            public_url=f"https://{hostname}",
            auth_username=auth_user,
            auth_password_hash=auth_hash,
            cloudflare_tunnel=args.tunnel,
            cloudflare_hostname=hostname,
            cloudflare_config=str(config_path),
        )
        write_session(session)
        ensure_mobile_index(session)
        patch_cloudflared_config(config_path, hostname, f"http://127.0.0.1:{proxy_port}")
        if not args.no_tmux:
            ensure_tmux_session(name, workdir, "codex" if args.codex else "")
        if not args.no_start:
            start_index_service(session.index_port, session.mode, session.api_bind_host)
            start_session_service(session)
        if args.route_dns:
            run(["cloudflared", "tunnel", "route", "dns", args.tunnel, hostname], check=False)
        sessions.append(session)
    for session in sessions:
        print(f"{session.name:18} {session_url(session)}  ttyd={session.port} proxy={session.proxy_port}")
    print(f"cloudflared config: {config_path}")
    print("restart cloudflared with: cloudflared tunnel run " + args.tunnel)


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
    parser.add_argument("--auth-password-env")
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
    verify.add_argument("name", nargs="?")
    verify.add_argument("--skip-network", action="store_true")
    verify.add_argument("--auth-password", help="password for authenticated proxy network checks")
    verify.add_argument("--local-test", action="store_true", help="run a full temporary tmux/ttyd/proxy integration test")
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

    proxy = sub.add_parser("proxy", help="configure, run, install, or verify a session proxy")
    proxy_sub = proxy.add_subparsers(dest="proxy_command", required=True)
    proxy_run = proxy_sub.add_parser("run", help="configure then run a local authenticated proxy")
    proxy_run.add_argument("name")
    proxy_run.add_argument("--bind-host")
    proxy_run.add_argument("--proxy-port", type=int)
    proxy_run.add_argument("--auth-user")
    proxy_run.add_argument("--auth-password")
    proxy_run.add_argument("--auth-password-env")
    proxy_run.set_defaults(func=cmd_proxy_run)
    proxy_install = proxy_sub.add_parser("install-service", help="configure proxy and install/start native services")
    proxy_install.add_argument("name")
    proxy_install.add_argument("--proxy-port", type=int)
    proxy_install.add_argument("--auth-user")
    proxy_install.add_argument("--auth-password")
    proxy_install.add_argument("--auth-password-env")
    proxy_install.add_argument("--generate-auth", action="store_true")
    proxy_install.set_defaults(func=cmd_proxy_install_service)
    proxy_verify = proxy_sub.add_parser("verify", help="verify a proxied session")
    proxy_verify.add_argument("name")
    proxy_verify.add_argument("--skip-network", action="store_true")
    proxy_verify.add_argument("--auth-password")
    proxy_verify.set_defaults(func=cmd_proxy_verify)

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

    auth = sub.add_parser("auth", help="manage PhoneCodex proxy auth env file")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_init = auth_sub.add_parser("init", help="create ~/.config/phonecodex/env with chmod 600")
    auth_init.add_argument("--user", default="phonecodex")
    auth_init.add_argument("--auth-password")
    auth_init.add_argument("--auth-password-env")
    auth_init.add_argument("--generate", action="store_true")
    auth_init.add_argument("--force", action="store_true")
    auth_init.set_defaults(func=cmd_auth)

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
    local.add_argument("--proxy-port", type=int)
    local.add_argument("--auth-user")
    local.add_argument("--auth-password")
    local.add_argument("--auth-password-env")
    local.add_argument("--generate-auth", action="store_true")
    local.set_defaults(func=cmd_deploy)
    tailscale = deploy_sub.add_parser("tailscale")
    tailscale.add_argument("name")
    tailscale.add_argument("--hostname")
    tailscale.add_argument("--proxy-port", type=int)
    tailscale.add_argument("--auth-user")
    tailscale.add_argument("--auth-password")
    tailscale.add_argument("--auth-password-env")
    tailscale.add_argument("--generate-auth", action="store_true")
    tailscale.add_argument("--serve", action="store_true")
    tailscale.set_defaults(func=cmd_deploy)
    cloudflare = deploy_sub.add_parser("cloudflare")
    cloudflare.add_argument("name")
    cloudflare.add_argument("--hostname")
    cloudflare.add_argument("--tunnel", required=True)
    cloudflare.add_argument("--config", "--cloudflared-config", default=str(Path.home() / ".cloudflared" / "config.yml"))
    cloudflare.add_argument("--proxy-port", type=int)
    cloudflare.add_argument("--auth-user")
    cloudflare.add_argument("--auth-password")
    cloudflare.add_argument("--auth-password-env")
    cloudflare.add_argument("--route-dns", action="store_true")
    cloudflare.add_argument("--base-hostname")
    cloudflare.add_argument("--count", type=int, default=1)
    cloudflare.add_argument("--start-port", type=int)
    cloudflare.add_argument("--start-proxy-port", type=int)
    cloudflare.add_argument("--host-pattern")
    cloudflare.add_argument("--session-prefix", default="phonecodex")
    cloudflare.add_argument("--directory")
    cloudflare.add_argument("--index-port", type=int, default=DEFAULT_INDEX_PORT)
    cloudflare.add_argument("--codex", action="store_true")
    cloudflare.add_argument("--no-start", action="store_true")
    cloudflare.add_argument("--no-tmux", action="store_true")
    cloudflare.set_defaults(func=cmd_deploy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0
