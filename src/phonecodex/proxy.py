from __future__ import annotations

import base64
import hashlib
import http.client
import http.server
import select
import socket
import socketserver
import threading
from dataclasses import dataclass

from .config import SessionConfig, read_session


@dataclass(frozen=True)
class ProxyTarget:
    host: str
    port: int


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_basic_auth(header: str, username: str, password_hash: str) -> bool:
    if not username or not password_hash:
        return True
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    supplied_user, sep, supplied_password = decoded.partition(":")
    if not sep or supplied_user != username:
        return False
    return hash_password(supplied_password) == password_hash


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    session: SessionConfig

    def _auth_ok(self) -> bool:
        return verify_basic_auth(
            self.headers.get("Authorization", ""),
            self.session.auth_username,
            self.session.auth_password_hash,
        )

    def _send_auth_required(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="PhoneCodex"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"authentication required\n")

    def _target_for_path(self) -> ProxyTarget:
        if self.path.startswith("/api/") or self.path.startswith("/mobile-toolbar.js"):
            return ProxyTarget(self.session.api_bind_host or "127.0.0.1", self.session.index_port)
        return ProxyTarget(self.session.ttyd_bind_host or "127.0.0.1", self.session.port)

    def _forward_headers(self, target: ProxyTarget) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in {"authorization", "proxy-authorization", "host"}:
                continue
            headers[key] = value
        headers["Host"] = f"{target.host}:{target.port}"
        if "Origin" in headers and target.port == self.session.port:
            headers["Origin"] = f"http://{target.host}:{target.port}"
        return headers

    def _proxy_http(self) -> None:
        target = self._target_for_path()
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        conn = http.client.HTTPConnection(target.host, target.port, timeout=20)
        try:
            conn.request(self.command, self.path, body=body, headers=self._forward_headers(target))
            response = conn.getresponse()
            data = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() in {"server", "date", "transfer-encoding"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            conn.close()

    def _proxy_upgrade(self) -> None:
        target = self._target_for_path()
        upstream = socket.create_connection((target.host, target.port), timeout=20)
        try:
            headers = self._forward_headers(target)
            header_lines = [f"{self.command} {self.path} {self.request_version}"]
            header_lines.extend(f"{key}: {value}" for key, value in headers.items())
            header_lines.append("")
            header_lines.append("")
            upstream.sendall("\r\n".join(header_lines).encode("utf-8"))

            sockets = [self.connection, upstream]
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                if exceptional:
                    break
                if not readable:
                    continue
                for sock in readable:
                    data = sock.recv(65536)
                    if not data:
                        return
                    (upstream if sock is self.connection else self.connection).sendall(data)
        finally:
            upstream.close()

    def _handle(self) -> None:
        if not self._auth_ok():
            self._send_auth_required()
            return
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._proxy_upgrade()
            return
        self._proxy_http()

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def log_message(self, format: str, *args: object) -> None:
        return


def serve_proxy(name: str, bind_host: str | None = None, port: int | None = None) -> None:
    session = read_session(name)

    class Handler(ProxyHandler):
        pass

    Handler.session = session
    bind = bind_host or session.proxy_bind_host or "127.0.0.1"
    listen_port = port or session.proxy_port
    if not listen_port:
        raise SystemExit(f"session has no proxy_port: {name}")
    with ReusableThreadingTCPServer((bind, listen_port), Handler) as httpd:
        print(f"PhoneCodex proxy listening on http://{bind}:{listen_port}/ for {name}", flush=True)
        httpd.serve_forever()

