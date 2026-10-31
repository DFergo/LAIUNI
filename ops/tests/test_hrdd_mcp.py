"""Tests for ops/hrdd_mcp.py — standard library only.

    python3 -m unittest discover -s ops/tests -v

A fake backend + frontend (http.server) records every request, so the gates can
be checked: nothing reaches the server without apply / confirmations, and no
secret comes back to the chat.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_HOME = tempfile.TemporaryDirectory()
os.environ["HRDD_OPS_HOME"] = _HOME.name
OPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OPS))

import hrdd_mcp as m  # noqa: E402

API_KEY = "sk-real-key-0123456789abcdef"


class Fake(BaseHTTPRequestHandler):
    requests: list = []
    admin_exists = False

    def log_message(self, *a):
        pass

    def _send(self, status, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        Fake.requests.append((self.command, self.path, body, dict(self.headers)))
        return body

    def do_GET(self):
        self._record()
        if self.path == "/admin/status":
            return self._send(200, {"setup_complete": Fake.admin_exists})
        if self.path.startswith("/internal/stream/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for part in ("Hello", " from the test model."):
                self.wfile.write(f"event: token\ndata: {part}\n\n".encode())
            self.wfile.write(b"event: done\ndata: \n\n")
            return
        if self.headers.get("Authorization") != "Bearer TOKEN":
            return self._send(401, {"detail": "no"})
        if self.path == "/admin/llm/connections":
            return self._send(200, {"connections": [{"id": "x", "api_key": API_KEY}]})
        return self._send(200, {"ok": True, "path": self.path})

    def do_POST(self):
        body = self._record()
        if self.path == "/admin/setup":
            Fake.admin_exists = True
            return self._send(200, {"status": "ok"})
        if self.path == "/admin/login":
            return self._send(200, {"token": "TOKEN", "expires_in": 3600})
        if self.path == "/internal/queue":
            return self._send(200, {"status": "queued"})
        return self._send(200, {"received": json.loads(body or b"{}")})

    do_PUT = do_POST

    def do_DELETE(self):
        self._record()
        self._send(200, {"deleted": True})


class McpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Fake.requests.clear()
        self.tmp = Path(tempfile.mkdtemp())

    def call(self, name, **args):
        out = m._call_tool(name, args)
        return out["isError"], out["content"][0]["text"]

    def _login(self):
        self.assertFalse(self.call("backend_connect", url=self.url)[0])
        m._save_state({**m._state(), "tokens": {self.url: "TOKEN"}})

    # ------------------------------------------------------------ protocol

    def test_stdio_protocol(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/get", "params": {"name": "start"}},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "hrdd://guides/overview"}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"},
        ]
        r = subprocess.run([sys.executable, str(OPS / "hrdd_mcp.py")], input="\n".join(json.dumps(x) for x in msgs),
                           capture_output=True, text=True, timeout=30, env={**os.environ})
        replies = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual([x["id"] for x in replies], [1, 2, 3, 4, 5])          # no reply to the notification
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "hrdd-helper")
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertTrue({"check_machine", "deploy_prepare", "admin_api", "test_smoke", "guide"} <= names)
        self.assertIn("guide('overview')", replies[2]["result"]["messages"][0]["content"]["text"])
        self.assertIn("Ask before every change", replies[3]["result"]["contents"][0]["text"])
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_every_guide_named_in_the_tools_exists(self):
        import re
        guides = {p.stem for p in (OPS / "guides").glob("*.md")}
        text = json.dumps(m.PROMPTS) + (OPS.parent / "SETUP-AGENT.md").read_text()
        text += " ".join(p.read_text() for p in (OPS / "guides").glob("*.md"))
        named = set(re.findall(r"guides? ?\(?['`]([a-z-]+)['`]", text))
        self.assertTrue(named)
        self.assertEqual(named - guides, set())

    # ------------------------------------------------------------ deployments

    def test_deploy_prepare_plans_then_writes_private_env_without_echoing_secrets(self):
        folder = self.tmp / "backend"
        err, plan = self.call("deploy_prepare", topology="backend", folder=str(folder))
        self.assertFalse(err)
        self.assertIn("planned", plan)
        self.assertFalse(folder.exists())                                   # nothing written without apply
        err, out = self.call("deploy_prepare", topology="backend", folder=str(folder), apply=True)
        self.assertFalse(err, out)
        env = m._read_env(folder / ".env")
        self.assertEqual(len(env["HRDD_FRONTEND_SECRET"]), 64)
        self.assertNotIn(env["HRDD_FRONTEND_SECRET"], out)                  # never returned
        self.assertEqual(stat.S_IMODE((folder / ".env").stat().st_mode), 0o600)
        # A frontend can take the backend's secret by reference, without it entering the chat
        fe = self.tmp / "front"
        err, out = self.call("deploy_prepare", topology="t2-vps-tailscale", folder=str(fe), apply=True, values={
            "TAILSCALE_IP": "100.64.0.9", "TUNNEL_TOKEN": "tok",
            "HRDD_BACKEND_SECRET": f"env:{folder}/.env#HRDD_FRONTEND_SECRET"})
        self.assertFalse(err, out)
        self.assertEqual(m._read_env(fe / ".env")["HRDD_BACKEND_SECRET"], env["HRDD_FRONTEND_SECRET"])
        self.assertNotIn(env["HRDD_FRONTEND_SECRET"], out)
        # A folder with a deployment is never overwritten
        self.assertTrue(self.call("deploy_prepare", topology="backend", folder=str(folder), apply=True)[0])

    def test_unknown_env_keys_are_refused(self):
        err, out = self.call("deploy_prepare", topology="t1-lan", folder=str(self.tmp / "x"), values={"NOPE": "1"})
        self.assertTrue(err)
        self.assertIn("NOPE", out)

    def test_secret_reveal_needs_confirmation(self):
        self.call("deploy_prepare", topology="backend", folder=str(self.tmp / "b"), apply=True)
        self.assertTrue(self.call("secret_reveal", folder=str(self.tmp / "b"), key="HRDD_FRONTEND_SECRET")[0])
        err, out = self.call("secret_reveal", folder=str(self.tmp / "b"), key="HRDD_FRONTEND_SECRET",
                             confirm_reveal=True)
        self.assertFalse(err)
        self.assertEqual(len(out), 64)

    def test_compose_changes_need_apply(self):
        self.call("deploy_prepare", topology="backend", folder=str(self.tmp / "c"), apply=True)
        err, out = self.call("compose", folder=str(self.tmp / "c"), action="down")
        self.assertFalse(err)
        self.assertIn("planned", out)
        self.assertNotIn("-v", json.loads(out)["planned"].split())          # never removes volumes

    # ------------------------------------------------------------ admin API

    def test_admin_create_keeps_password_off_the_chat(self):
        Fake.admin_exists = False
        self.call("backend_connect", url=self.url)
        err, plan = self.call("admin_create")
        self.assertIn("planned", plan)
        self.assertFalse(any(r[1] == "/admin/setup" for r in Fake.requests))
        err, out = self.call("admin_create", apply=True)
        self.assertFalse(err, out)
        pw_file = Path(json.loads(out)["password_file"])
        password = pw_file.read_text().strip()
        self.assertNotIn(password, out)
        self.assertEqual(stat.S_IMODE(pw_file.stat().st_mode), 0o600)
        self.assertEqual(json.loads([r for r in Fake.requests if r[1] == "/admin/login"][0][2])["password"], password)

    def test_changes_are_planned_until_apply(self):
        self._login()
        err, out = self.call("admin_api", method="PUT", path="/admin/llm/settings", body={"inference_model": "m"})
        self.assertIn("planned", out)
        self.assertFalse(any(r[0] == "PUT" for r in Fake.requests))
        err, out = self.call("admin_api", method="PUT", path="/admin/llm/settings", body={"inference_model": "m"},
                             apply=True)
        self.assertFalse(err, out)
        self.assertTrue(any(r[0] == "PUT" for r in Fake.requests))

    def test_destructive_needs_confirmation(self):
        self._login()
        for method, path in (("DELETE", "/admin/frontends/abc"), ("POST", "/admin/sessions/purge/abc"),
                             ("POST", "/admin/rag/reset-defaults")):
            err, out = self.call("admin_api", method=method, path=path, apply=True)
            self.assertTrue(err, path)
        self.assertEqual([r for r in Fake.requests if r[0] != "GET"], [])
        err, _ = self.call("admin_api", method="DELETE", path="/admin/frontends/abc", apply=True,
                           confirm_destructive=True)
        self.assertFalse(err)

    def test_session_content_needs_confirmation(self):
        self._login()
        for path in ("/admin/sessions/ALPINE-4523", "/admin/sessions/ALPINE-4523/documents", "/admin/export/global"):
            self.assertTrue(self.call("admin_api", method="GET", path=path)[0], path)
        self.assertFalse(self.call("admin_api", method="GET", path="/admin/sessions")[0])        # list: metadata
        self.assertFalse(self.call("admin_api", method="GET", path="/admin/sessions/lifecycle")[0])
        self.assertFalse(self.call("admin_api", method="GET", path="/admin/sessions/ALPINE-4523",
                                   confirm_content=True)[0])

    def test_env_references_are_resolved_locally_and_secrets_masked(self):
        self._login()
        keys = self.tmp / "keys.env"
        keys.write_text(f"MISTRAL_API_KEY={API_KEY}\n")
        body = {"id": "mistral", "type": "openai", "base_url": "https://api.mistral.ai/v1",
                "api_key": f"env:{keys}#MISTRAL_API_KEY"}
        err, plan = self.call("admin_api", method="POST", path="/admin/llm/connections", body=body)
        self.assertNotIn(API_KEY, plan)
        err, out = self.call("admin_api", method="POST", path="/admin/llm/connections", body=body, apply=True)
        self.assertFalse(err, out)
        sent = json.loads([r for r in Fake.requests if r[0] == "POST"][-1][2])
        self.assertEqual(sent["api_key"], API_KEY)                          # the backend got the real key
        self.assertNotIn(API_KEY, out)                                      # the chat did not
        err, out = self.call("admin_api", method="GET", path="/admin/llm/connections")
        self.assertNotIn(API_KEY, out)

    def test_not_logged_in_is_explained(self):
        self.call("backend_connect", url=self.url)
        m._save_state({**m._state(), "tokens": {}})
        err, out = self.call("admin_api", method="GET", path="/admin/frontends")
        self.assertTrue(err)
        self.assertIn("login", out)

    # ------------------------------------------------------------ tests

    def test_smoke_reads_the_streamed_reply(self):
        err, out = self.call("test_smoke", public_url=self.url, timeout_s=20)
        self.assertFalse(err, out)
        result = json.loads(out)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "Hello from the test model.")
        queued = json.loads([r for r in Fake.requests if r[1] == "/internal/queue"][0][2])
        self.assertTrue(queued["session_token"].startswith("SMOKE-"))
        self.assertEqual(queued["survey"]["role"], "worker")


if __name__ == "__main__":
    unittest.main()
