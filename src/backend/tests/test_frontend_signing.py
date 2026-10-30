"""Tests for signed backend → frontend calls (services/frontend_client.py) and
the frontend credentials in the admin API.

Run inside the backend container:
    cd /app && python -m unittest src.tests.test_frontend_signing -v
"""

import asyncio
import os
import tempfile
import unittest

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

import httpx  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from src.services import frontend_client  # noqa: E402
from src.services import frontend_registry as reg  # noqa: E402
from src.api.v1.admin import frontends as fe  # noqa: E402

SECRET = "k" * 48


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Capture:
    """httpx MockTransport that records the last request."""

    def __init__(self, status: int = 200):
        self.requests: list[httpx.Request] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json={"ok": True})


class SignTest(unittest.TestCase):
    def test_shared_vector(self):
        # Same vector as src/frontend/sidecar/tests/test_backend_surface.py
        body = b'{"token":"AB12-CD34","status":"not_found","data":null}'
        sig = frontend_client.sign("0123456789abcdef0123456789abcdef", "1767225600", "n-0001", "POST",
                                   "/backend/v1/session/AB12-CD34/recovery-data", body)
        self.assertEqual(sig, "v1=c8cfb97d1391eebf7dab6c476c36fd64c7594c11204ef2ef1411b478e23c5a02")


class RegistryAuthTest(unittest.TestCase):
    def setUp(self):
        reg.registry._frontends = {}
        frontend_client._warned_unsigned.clear()

    def tearDown(self):
        reg.registry._frontends = {}

    def _client(self, cap: _Capture) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(cap), auth=frontend_client._RegistryAuth())

    def test_signed_frontend_rewritten_and_signed(self):
        f = reg.registry.register("https://fe1-backend.example.org", "VPS")
        reg.registry.update(f["id"], signing_secret=SECRET,
                            extra_headers={"CF-Access-Client-Id": "id.access", "CF-Access-Client-Secret": "sec"})
        cap = _Capture()

        async def go():
            async with self._client(cap) as c:
                await c.post("https://fe1-backend.example.org/internal/stream/T-1/chunk", json={"event": "token", "data": "x"})
        _run(go())

        req = cap.requests[0]
        self.assertEqual(req.url.path, "/backend/v1/stream/T-1/chunk")
        self.assertEqual(req.headers["CF-Access-Client-Id"], "id.access")
        expected = frontend_client.sign(SECRET, req.headers["X-HRDD-Timestamp"], req.headers["X-HRDD-Nonce"],
                                        "POST", "/backend/v1/stream/T-1/chunk", req.content)
        self.assertEqual(req.headers["X-HRDD-Signature"], expected)

    def test_multipart_body_is_signed(self):
        f = reg.registry.register("http://10.0.0.20:8081", "LAN")
        reg.registry.update(f["id"], signing_secret=SECRET)
        cap = _Capture()

        async def go():
            async with self._client(cap) as c:
                await c.post("http://10.0.0.20:8081/internal/branding-logo", data={"mode": "white"},
                             files={"color": ("logo.png", b"\x89PNG...", "image/png")})
        _run(go())
        req = cap.requests[0]
        expected = frontend_client.sign(SECRET, req.headers["X-HRDD-Timestamp"], req.headers["X-HRDD-Nonce"],
                                        "POST", "/backend/v1/branding-logo", req.content)
        self.assertEqual(req.headers["X-HRDD-Signature"], expected)

    def test_unsigned_frontend_left_untouched(self):
        reg.registry.register("http://10.0.0.30:8090", "legacy")
        cap = _Capture()

        async def go():
            async with self._client(cap) as c:
                await c.get("http://10.0.0.30:8090/internal/queue")
        _run(go())
        req = cap.requests[0]
        self.assertEqual(req.url.path, "/internal/queue")
        self.assertNotIn("X-HRDD-Signature", req.headers)

    def test_unknown_url_untouched(self):
        cap = _Capture()

        async def go():
            async with self._client(cap) as c:
                await c.get("http://elsewhere:1234/internal/queue")
        _run(go())
        self.assertNotIn("X-HRDD-Signature", cap.requests[0].headers)

    def test_prefix_match_does_not_cross_ports(self):
        f = reg.registry.register("http://h:808", "A")
        reg.registry.update(f["id"], signing_secret=SECRET)
        cap = _Capture()

        async def go():
            async with self._client(cap) as c:
                await c.get("http://h:8081/internal/queue")
        _run(go())
        self.assertNotIn("X-HRDD-Signature", cap.requests[0].headers)


class AdminCredentialsTest(unittest.TestCase):
    def setUp(self):
        reg.registry._frontends = {}
        self._orig_probe = fe._probe
        self.probed: list[tuple] = []

        async def fake_probe(url, secret, headers):
            self.probed.append((url, secret, headers))
        fe._probe = fake_probe

    def tearDown(self):
        fe._probe = self._orig_probe
        reg.registry._frontends = {}

    def test_register_with_credentials_hides_secret(self):
        res = _run(fe.register_frontend(fe.RegisterRequest(
            url="https://fe1-backend.example.org/", name="VPS", signing_secret=SECRET,
            extra_headers={"CF-Access-Client-Id": "a", "CF-Access-Client-Secret": "b"}), _={}))
        view = res["frontend"]
        self.assertTrue(view["signing_enabled"])
        self.assertEqual(view["extra_header_names"], ["CF-Access-Client-Id", "CF-Access-Client-Secret"])
        self.assertNotIn("signing_secret", view)
        self.assertNotIn("extra_headers", view)
        self.assertEqual(self.probed[0][1], SECRET)  # probe used the secret
        stored = reg.registry.get(view["id"])
        self.assertEqual(stored["signing_secret"], SECRET)
        listed = _run(fe.list_frontends(_={}))["frontends"][0]
        self.assertNotIn("signing_secret", listed)

    def test_short_secret_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _run(fe.register_frontend(fe.RegisterRequest(url="http://a:8081", signing_secret="short"), _={}))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_legacy_entry_gets_secret_later(self):
        fid = reg.registry.register("http://10.0.0.30:8090", "legacy")["id"]
        self.assertFalse(fe._public_view(reg.registry.get(fid))["signing_enabled"])
        res = _run(fe.update_frontend(fid, fe.UpdateRequest(url="http://10.0.0.30:8081", signing_secret=SECRET), verify=True, _={}))
        self.assertTrue(res["frontend"]["signing_enabled"])
        self.assertEqual(self.probed[-1], ("http://10.0.0.30:8081", SECRET, None))

    def test_name_only_update_does_not_probe(self):
        fid = reg.registry.register("http://a:8081", "old")["id"]
        _run(fe.update_frontend(fid, fe.UpdateRequest(name="new"), verify=True, _={}))
        self.assertEqual(self.probed, [])


if __name__ == "__main__":
    unittest.main()
