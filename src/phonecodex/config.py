from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import errno
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_INDEX_PORT = 7680
DEFAULT_PROXY_PORT = 8780
DEFAULT_ENV_FILE_NAME = "env"
PORT_START = 7681
PORT_END = 7780
PROXY_PORT_START = 8781
PROXY_PORT_END = 8880
MAX_PASTE_BYTES = 512 * 1024
SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
DEPLOYMENT_MODES = {"local", "tailscale", "cloudflare"}
SERVICE_PATH = (
    os.environ.get("PHONECODEX_SERVICE_PATH")
    or "/opt/homebrew/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
)


@dataclass(frozen=True)
class SessionConfig:
    name: str
    port: int
    title: str
    tmux_session: str
    workdir: str
    index_port: int = DEFAULT_INDEX_PORT
    mode: str = "tailscale"
    ttyd_bind_host: str = ""
    api_bind_host: str = ""
    proxy_enabled: bool = False
    proxy_port: int = 0
    proxy_bind_host: str = "127.0.0.1"
    api_base: str = "index"
    public_url: str = ""
    auth_username: str = ""
    auth_password_hash: str = ""
    cloudflare_tunnel: str = ""
    cloudflare_hostname: str = ""
    cloudflare_config: str = ""


def normalize_session(data: dict[str, object]) -> SessionConfig:
    values = dict(data)
    values.setdefault("index_port", DEFAULT_INDEX_PORT)
    values.setdefault("mode", "tailscale")
    values.setdefault("ttyd_bind_host", "")
    values.setdefault("api_bind_host", "")
    values.setdefault("proxy_enabled", False)
    values.setdefault("proxy_port", 0)
    values.setdefault("proxy_bind_host", "127.0.0.1")
    values.setdefault("api_base", "index")
    values.setdefault("public_url", "")
    values.setdefault("auth_username", "")
    values.setdefault("auth_password_hash", "")
    values.setdefault("cloudflare_tunnel", "")
    values.setdefault("cloudflare_hostname", "")
    values.setdefault("cloudflare_config", "")
    return SessionConfig(**values)


def config_dir() -> Path:
    override = os.environ.get("PHONECODEX_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "phonecodex"
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "phonecodex"
    return Path.home() / ".config" / "phonecodex"


def sessions_dir() -> Path:
    return config_dir() / "sessions"


def assets_dir() -> Path:
    return config_dir() / "assets"


def env_file_path() -> Path:
    return config_dir() / DEFAULT_ENV_FILE_NAME


def mobile_index_path(index_port: int = DEFAULT_INDEX_PORT) -> Path:
    return assets_dir() / f"mobile-index-{index_port}.html"


def session_mobile_index_path(name: str) -> Path:
    validate_name(name)
    return assets_dir() / f"mobile-index-{name}.html"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
    assets_dir().mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(config_dir(), 0o700)
        os.chmod(sessions_dir(), 0o700)


def parse_env_file(path: Path | None = None) -> dict[str, str]:
    override = os.environ.get("PHONECODEX_ENV_FILE")
    target = path or (Path(override).expanduser() if override else env_file_path())
    if not target.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            values[key] = value
    return values


def ensure_env_file(user: str = "phonecodex", password: str = "") -> Path:
    ensure_dirs()
    path = env_file_path()
    if not path.exists():
        lines = [f"PHONECODEX_AUTH_USER={user}"]
        if password:
            lines.append(f"PHONECODEX_AUTH_PASSWORD={password}")
        else:
            lines.append("PHONECODEX_AUTH_PASSWORD=")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def validate_name(name: str) -> None:
    if not SESSION_NAME_RE.fullmatch(name or ""):
        raise SystemExit("NAME must use only letters, numbers, dot, dash, and underscore")


def session_path(name: str) -> Path:
    validate_name(name)
    return sessions_dir() / f"{name}.json"


def read_session(name: str) -> SessionConfig:
    path = session_path(name)
    if not path.exists():
        raise SystemExit(f"session not found: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return normalize_session(data)


def write_session(session: SessionConfig) -> None:
    ensure_dirs()
    path = session_path(session.name)
    path.write_text(json.dumps(asdict(session), indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)


def all_sessions() -> list[SessionConfig]:
    ensure_dirs()
    sessions = []
    for path in sorted(sessions_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sessions.append(normalize_session(data))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return sessions


def find_session_by_port(port: str | int) -> SessionConfig | None:
    try:
        wanted = int(port)
    except (TypeError, ValueError):
        return None
    for session in all_sessions():
        if session.port == wanted or session.proxy_port == wanted:
            return session
    return None


def command_path(command: str, path: str | None = None) -> str:
    return shutil.which(command, path=path) or ""


def command_exists(command: str, path: str | None = None) -> bool:
    return bool(command_path(command, path))


def run_text(command: list[str], timeout: float = 5) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def tailscale_ip() -> str:
    if not command_exists("tailscale"):
        return ""
    output = run_text(["tailscale", "ip", "-4"])
    return output.splitlines()[0].strip() if output.splitlines() else ""


def tailscale_dns_name() -> str:
    if not command_exists("tailscale"):
        return ""
    output = run_text(["tailscale", "status", "--json"], timeout=8)
    if not output:
        return ""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return ""
    dns_name = data.get("Self", {}).get("DNSName", "")
    return str(dns_name).rstrip(".")


def local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def default_bind_host() -> str:
    override = os.environ.get("PHONECODEX_BIND_HOST")
    if override:
        return override
    return tailscale_ip() or "127.0.0.1"


def bind_host_for_mode(mode: str) -> str:
    if mode in {"local", "cloudflare"}:
        return "127.0.0.1"
    if mode == "tailscale":
        return tailscale_ip() or "127.0.0.1"
    return default_bind_host()


def display_host() -> str:
    return tailscale_dns_name() or tailscale_ip() or local_lan_ip()


def display_host_for_session(session: SessionConfig) -> str:
    if session.public_url:
        return session.public_url.rstrip("/")
    if session.mode == "local":
        return "127.0.0.1"
    return display_host()


def port_bind_state(host: str, port: int) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return "available"
    except OSError as error:
        if error.errno in {errno.EADDRINUSE, errno.EACCES}:
            return "used"
        # Sandboxed agent environments may forbid bind() entirely. Treat that
        # as unknown instead of claiming every port is busy.
        return "unknown"


def choose_port(existing: SessionConfig | None = None, bind_host: str = "127.0.0.1") -> int:
    if existing is not None:
        return existing.port
    used = {session.port for session in all_sessions()}
    for port in range(PORT_START, PORT_END + 1):
        if port in used:
            continue
        state = port_bind_state(bind_host, port)
        if state in {"available", "unknown"}:
            return port
    raise SystemExit(f"no available port in {PORT_START}-{PORT_END}")


def choose_proxy_port(existing: SessionConfig | None = None, bind_host: str = "127.0.0.1") -> int:
    if existing is not None and existing.proxy_port:
        return existing.proxy_port
    used = {session.proxy_port for session in all_sessions() if session.proxy_port}
    for port in range(PROXY_PORT_START, PROXY_PORT_END + 1):
        if port in used:
            continue
        state = port_bind_state(bind_host, port)
        if state in {"available", "unknown"}:
            return port
    raise SystemExit(f"no available proxy port in {PROXY_PORT_START}-{PROXY_PORT_END}")


def python_command() -> str:
    return sys.executable


def is_wsl() -> bool:
    if platform.system().lower() != "linux":
        return False
    try:
        text = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in text or "wsl" in text
