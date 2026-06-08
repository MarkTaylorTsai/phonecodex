from __future__ import annotations

import html
import http.server
import json
import socketserver
import subprocess
import urllib.parse

from .config import (
    DEFAULT_INDEX_PORT,
    MAX_PASTE_BYTES,
    SessionConfig,
    all_sessions,
    default_bind_host,
    display_host,
    find_session_by_port,
    read_session,
)
from .toolbar import toolbar_js

KEY_MAP = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pgup": "PageUp",
    "pgdn": "PageDown",
    "enter": "Enter",
    "tab": "Tab",
    "esc": "Escape",
    "backspace": "BSpace",
    "delete": "Delete",
    "ctrl-c": "C-c",
    "ctrl-d": "C-d",
    "ctrl-a": "C-a",
    "ctrl-e": "C-e",
    "ctrl-u": "C-u",
    "ctrl-k": "C-k",
    "ctrl-l": "C-l",
}


def tmux_session_exists(name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def tmux_send_key(name: str, key: str) -> None:
    mapped = KEY_MAP.get(key)
    if mapped is None:
        raise ValueError("unsupported key")
    subprocess.run(["tmux", "send-keys", "-t", name, mapped], check=True)


def tmux_paste_text(name: str, text: str, submit: bool = False) -> None:
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_PASTE_BYTES:
        raise ValueError("paste is too large")
    subprocess.run(
        ["tmux", "load-buffer", "-b", "phonecodex-paste", "-"],
        input=encoded,
        check=True,
    )
    subprocess.run(
        ["tmux", "paste-buffer", "-d", "-p", "-r", "-b", "phonecodex-paste", "-t", name],
        check=True,
    )
    if submit:
        subprocess.run(["tmux", "send-keys", "-t", name, "Enter"], check=True)


def tmux_capture(name: str) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-S", "-200", "-t", name],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def active_state(session: SessionConfig) -> str:
    if tmux_session_exists(session.tmux_session):
        return "tmux"
    return "stopped"


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True


class Handler(http.server.BaseHTTPRequestHandler):
    index_port = DEFAULT_INDEX_PORT

    def add_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_text(self, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        encoded = text.encode("utf-8")
        self.send_response(status)
        self.add_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        self.send_text(status, json.dumps(payload), "application/json; charset=utf-8")

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_PASTE_BYTES + 8192:
            raise ValueError("request is too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.add_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/mobile-toolbar.js":
            self.send_text(200, toolbar_js(self.index_port), "application/javascript; charset=utf-8")
            return

        if parsed.path == "/api/session":
            query = urllib.parse.parse_qs(parsed.query)
            port = query.get("port", [""])[0]
            session = find_session_by_port(port)
            if session is None:
                self.send_json(404, {"error": "session not found"})
                return
            self.send_json(
                200,
                {
                    "name": session.name,
                    "port": session.port,
                    "dir": session.workdir,
                    "tmux_session": session.tmux_session,
                },
            )
            return

        if parsed.path == "/api/capture":
            query = urllib.parse.parse_qs(parsed.query)
            name = query.get("session", [""])[0]
            try:
                session = read_session(name)
            except SystemExit:
                self.send_json(404, {"error": "session not found"})
                return
            if not tmux_session_exists(session.tmux_session):
                self.send_json(404, {"error": "tmux session not found"})
                return
            try:
                self.send_json(200, {"text": tmux_capture(session.tmux_session)})
            except subprocess.CalledProcessError:
                self.send_json(500, {"error": "capture failed"})
            return

        if parsed.path not in {"/", "/index.html"}:
            self.send_error(404)
            return

        host = display_host()
        rows = "\n".join(
            "<tr>"
            f"<td><a href=\"http://{html.escape(host)}:{session.port}/\">{html.escape(session.name)}</a></td>"
            f"<td>{session.port}</td>"
            f"<td>{html.escape(active_state(session))}</td>"
            f"<td>{html.escape(session.workdir)}</td>"
            f"<td><code>phonecodex attach {html.escape(session.name)}</code></td>"
            "</tr>"
            for session in all_sessions()
        )
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="15">
  <title>PhoneCodex Sessions</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; background: #101114; color: #f4f4f5; }}
    h1 {{ font-size: 22px; margin: 0 0 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #2a2d34; padding: 10px 8px; text-align: left; }}
    th {{ color: #a1a1aa; font-weight: 600; }}
    a {{ color: #7dd3fc; text-decoration: none; font-weight: 600; }}
    code {{ color: #d4d4d8; }}
  </style>
</head>
<body>
  <h1>PhoneCodex Sessions</h1>
  <table>
    <thead><tr><th>Name</th><th>Port</th><th>Status</th><th>Directory</th><th>Desktop</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
        self.send_text(200, body, "text/html; charset=utf-8")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
            return

        try:
            session = read_session(str(payload.get("session", "")))
        except SystemExit:
            self.send_json(404, {"error": "session not found"})
            return
        if not tmux_session_exists(session.tmux_session):
            self.send_json(404, {"error": "tmux session not found"})
            return

        try:
            if parsed.path == "/api/key":
                tmux_send_key(session.tmux_session, str(payload.get("key", "")))
                self.send_json(200, {"ok": True})
                return
            if parsed.path == "/api/paste":
                tmux_paste_text(
                    session.tmux_session,
                    str(payload.get("text", "")),
                    bool(payload.get("submit", False)),
                )
                self.send_json(200, {"ok": True})
                return
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        except subprocess.CalledProcessError:
            self.send_json(500, {"error": "tmux command failed"})
            return

        self.send_json(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        return


def serve_index(bind_host: str | None = None, index_port: int = DEFAULT_INDEX_PORT) -> None:
    bind = bind_host or default_bind_host()
    Handler.index_port = index_port
    with ReusableThreadingTCPServer((bind, index_port), Handler) as httpd:
        print(f"PhoneCodex index listening on http://{bind}:{index_port}/", flush=True)
        httpd.serve_forever()

