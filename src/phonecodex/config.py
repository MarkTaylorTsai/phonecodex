from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import errno
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_INDEX_PORT = 7680
PORT_START = 7681
PORT_END = 7780
MAX_PASTE_BYTES = 512 * 1024
SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SessionConfig:
    name: str
    port: int
    title: str
    tmux_session: str
    workdir: str
    index_port: int = DEFAULT_INDEX_PORT


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


def mobile_index_path(index_port: int = DEFAULT_INDEX_PORT) -> Path:
    return assets_dir() / f"mobile-index-{index_port}.html"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
    assets_dir().mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(config_dir(), 0o700)
        os.chmod(sessions_dir(), 0o700)


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
    return SessionConfig(**data)


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
            sessions.append(SessionConfig(**data))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return sessions


def find_session_by_port(port: str | int) -> SessionConfig | None:
    try:
        wanted = int(port)
    except (TypeError, ValueError):
        return None
    for session in all_sessions():
        if session.port == wanted:
            return session
    return None


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_text(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout.strip()


def tailscale_ip() -> str:
    if not command_exists("tailscale"):
        return ""
    output = run_text(["tailscale", "ip", "-4"])
    return output.splitlines()[0].strip() if output.splitlines() else ""


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


def display_host() -> str:
    return tailscale_ip() or local_lan_ip()


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


def python_command() -> str:
    return sys.executable
