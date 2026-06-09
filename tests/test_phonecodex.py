from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phonecodex import cli, server
from phonecodex.config import SessionConfig, env_file_path, parse_env_file, read_session, session_path, write_session
from phonecodex.config import ensure_env_file
from phonecodex.proxy import ProxyHandler, hash_password, verify_basic_auth


class PhoneCodexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_config_dir = os.environ.get("PHONECODEX_CONFIG_DIR")
        os.environ["PHONECODEX_CONFIG_DIR"] = self.temp.name

    def tearDown(self) -> None:
        if self.old_config_dir is None:
            os.environ.pop("PHONECODEX_CONFIG_DIR", None)
        else:
            os.environ["PHONECODEX_CONFIG_DIR"] = self.old_config_dir
        self.temp.cleanup()

    def make_session(self, **overrides: object) -> SessionConfig:
        values = {
            "name": "demo",
            "port": 7777,
            "title": "demo",
            "tmux_session": "demo",
            "workdir": self.temp.name,
            "index_port": 7878,
        }
        values.update(overrides)
        return SessionConfig(**values)

    def test_old_session_json_is_still_readable(self) -> None:
        path = session_path("old")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "name": "old",
                    "port": 7681,
                    "title": "old",
                    "tmux_session": "old",
                    "workdir": self.temp.name,
                }
            ),
            encoding="utf-8",
        )

        session = read_session("old")

        self.assertEqual(session.mode, "tailscale")
        self.assertFalse(session.proxy_enabled)
        self.assertEqual(session.api_base, "index")

    def test_mobile_index_uses_origin_for_proxy_mode(self) -> None:
        session = self.make_session(proxy_enabled=True, proxy_port=8787, api_base="origin")
        write_session(session)

        html = cli.ensure_mobile_index(session).read_text(encoding="utf-8")

        self.assertIn('window.PHONECODEX_SESSION_NAME = "demo"', html)
        self.assertIn("window.PHONECODEX_API_BASE = location.origin", html)
        self.assertIn("pcx-paste-ask", html)

    def test_mobile_index_uses_index_port_without_proxy(self) -> None:
        session = self.make_session(proxy_enabled=False, api_base="index")
        write_session(session)

        html = cli.ensure_mobile_index(session).read_text(encoding="utf-8")

        self.assertIn("location.protocol + '//' + location.hostname + ':7878'", html)
        self.assertNotIn("window.PHONECODEX_API_BASE = location.origin", html)

    def test_proxy_basic_auth(self) -> None:
        header = "Basic " + base64.b64encode(b"user:secret").decode("ascii")

        self.assertTrue(verify_basic_auth(header, "user", hash_password("secret")))
        self.assertFalse(verify_basic_auth(header, "user", hash_password("wrong")))
        self.assertFalse(verify_basic_auth("", "user", hash_password("secret")))
        self.assertTrue(verify_basic_auth("", "", ""))

    def test_tmux_paste_uses_targeted_literal_send_keys(self) -> None:
        calls: list[list[str]] = []

        def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            return subprocess.CompletedProcess(args, 0)

        with mock.patch.object(server.subprocess, "run", fake_run):
            server.tmux_paste_text("demo", "hello\nworld", submit=True)

        self.assertIn(["tmux", "send-keys", "-t", "demo:0.0", "-l", "hello"], calls)
        self.assertIn(["tmux", "send-keys", "-t", "demo:0.0", "-l", "world"], calls)
        self.assertEqual(calls.count(["tmux", "send-keys", "-t", "demo:0.0", "Enter"]), 2)

    def test_deploy_local_proxy_assigns_proxy_port(self) -> None:
        cli.main(["add", "demo", self.temp.name, "--mode", "local", "--port", "7766", "--no-start", "--no-tmux"])

        cli.main(["deploy", "local", "demo", "--proxy"])
        session = read_session("demo")

        self.assertEqual(session.mode, "local")
        self.assertTrue(session.proxy_enabled)
        self.assertGreater(session.proxy_port, 0)
        self.assertEqual(session.api_base, "origin")
        self.assertEqual(session.ttyd_bind_host, "127.0.0.1")
        self.assertEqual(session.api_bind_host, "127.0.0.1")

    def test_cloudflare_config_patch_adds_named_tunnel_ingress(self) -> None:
        path = Path(self.temp.name) / "cloudflared.yml"
        path.write_text("tunnel: phonecodex\ningress:\n  - service: http_status:404\n", encoding="utf-8")

        cli.patch_cloudflared_config(path, "phonecodex.example.com", "http://127.0.0.1:8781")

        text = path.read_text(encoding="utf-8")
        self.assertIn("hostname: phonecodex.example.com", text)
        self.assertIn("service: http://127.0.0.1:8781", text)
        self.assertIn("service: http_status:404", text)

    def test_auth_init_writes_env_file(self) -> None:
        cli.main(["auth", "init", "--user", "phonecodex", "--auth-password", "secret"])

        values = parse_env_file()

        self.assertEqual(values["PHONECODEX_AUTH_USER"], "phonecodex")
        self.assertEqual(values["PHONECODEX_AUTH_PASSWORD"], "secret")
        self.assertTrue(env_file_path().exists())

    def test_auth_init_does_not_overwrite_without_force(self) -> None:
        cli.main(["auth", "init", "--user", "phonecodex", "--auth-password", "first"])
        cli.main(["auth", "init", "--user", "phonecodex", "--auth-password", "second"])

        self.assertEqual(parse_env_file()["PHONECODEX_AUTH_PASSWORD"], "first")

    def test_auth_password_env_hashes_session_password(self) -> None:
        os.environ["PCX_TEST_PASSWORD"] = "from-env"
        self.addCleanup(lambda: os.environ.pop("PCX_TEST_PASSWORD", None))

        cli.main(
            [
                "add",
                "envpass",
                self.temp.name,
                "--mode",
                "cloudflare",
                "--cloudflare-hostname",
                "pcx.example.com",
                "--cloudflare-tunnel",
                "pcx",
                "--auth-user",
                "phonecodex",
                "--auth-password-env",
                "PCX_TEST_PASSWORD",
                "--no-start",
                "--no-tmux",
            ]
        )
        session = read_session("envpass")

        self.assertEqual(session.auth_username, "phonecodex")
        self.assertEqual(session.auth_password_hash, hash_password("from-env"))

    def test_generated_deploy_auth_fills_empty_env_file(self) -> None:
        ensure_env_file("phonecodex", "")
        cli.main(["add", "demo", self.temp.name, "--mode", "local", "--port", "7766", "--no-start", "--no-tmux"])

        cli.main(
            [
                "deploy",
                "cloudflare",
                "demo",
                "--hostname",
                "phonecodex.example.com",
                "--tunnel",
                "pcx",
                "--config",
                str(Path(self.temp.name) / "cloudflared.yml"),
            ]
        )
        values = parse_env_file()

        self.assertEqual(values["PHONECODEX_AUTH_USER"], "phonecodex")
        self.assertGreater(len(values["PHONECODEX_AUTH_PASSWORD"]), 20)

    def test_proxy_rewrites_public_session_port(self) -> None:
        session = self.make_session(proxy_enabled=True, proxy_port=8787)
        handler = object.__new__(ProxyHandler)
        handler.session = session
        handler.path = "/api/session?port=443"

        self.assertEqual(handler._backend_path(), "/api/session?port=8787")

    def test_cloudflare_multi_creates_sessions_and_ingress(self) -> None:
        config = Path(self.temp.name) / "cloudflared.yml"
        cli.main(
            [
                "deploy",
                "cloudflare",
                "multi",
                "--tunnel",
                "pcx",
                "--base-hostname",
                "phonecodex.example.com",
                "--count",
                "3",
                "--start-port",
                "9001",
                "--start-proxy-port",
                "9101",
                "--directory",
                self.temp.name,
                "--config",
                str(config),
                "--auth-user",
                "phonecodex",
                "--auth-password",
                "secret",
                "--no-start",
                "--no-tmux",
            ]
        )

        first = read_session("phonecodex")
        second = read_session("phonecodex-2")
        third = read_session("phonecodex-3")
        text = config.read_text(encoding="utf-8")

        self.assertEqual(first.port, 9001)
        self.assertEqual(second.proxy_port, 9102)
        self.assertEqual(third.cloudflare_hostname, "phonecodex3.example.com")
        self.assertIn("hostname: phonecodex.example.com", text)
        self.assertIn("hostname: phonecodex2.example.com", text)
        self.assertIn("hostname: phonecodex3.example.com", text)


if __name__ == "__main__":
    unittest.main()
