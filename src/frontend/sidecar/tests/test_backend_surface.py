"""Tests for the two sidecar surfaces and the backend-surface signature.

Run inside the frontend container (or any Python 3.11 env with the sidecar deps + httpx):
    cd /app && python -m unittest sidecar.tests.test_backend_surface -v
"""

import os
import secrets as pysecrets
import time
import unittest

SECRET = "s" * 40
PREVIOUS = "p" * 40
os.environ["HRDD_BACKEND_SECRET"] = SECRET
os.environ["HRDD_BACKEND_SECRET_PREVIOUS"] = PREVIOUS
os.environ.pop("ALLOW_UNSIGNED_BACKEND_SURFACE", None)

from fastapi import FastAPI, Form  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sidecar import backend_auth  # noqa: E402
from sidecar.main import app, backend_app  # noqa: E402


def signed_headers(method: str, path_qs: str, body: bytes = b"", secret: str = SECRET,
                   ts: int | None = None, nonce: str | None = None) -> dict[str, str]:
    ts_s = str(int(time.time()) if ts is None else ts)
    nonce = nonce or pysecrets.token_urlsafe(18)
    return {
        "X-HRDD-Timestamp": ts_s,
        "X-HRDD-Nonce": nonce,
        "X-HRDD-Signature": backend_auth.sign(secret, ts_s, nonce, method, path_qs, body),
    }


class SignatureVectorTest(unittest.TestCase):
    """Shared vector — the backend client and the forks must produce the same value."""

    def test_vector(self):
        body = b'{"token":"AB12-CD34","status":"not_found","data":null}'
        sig = backend_auth.sign("0123456789abcdef0123456789abcdef", "1767225600", "n-0001", "POST",
                                "/backend/v1/session/AB12-CD34/recovery-data", body)
        self.assertEqual(sig, "v1=c8cfb97d1391eebf7dab6c476c36fd64c7594c11204ef2ef1411b478e23c5a02")


class BackendSurfaceTest(unittest.TestCase):
    def setUp(self):
        # The middleware is built lazily per TestClient app instance; force a fresh one
        # (fresh nonce cache, start time) for each test.
        backend_app.middleware_stack = None
        self.client = TestClient(backend_app)
        # Build the middleware now (records its start time) so every signature
        # made inside a test is not "signed before the process started".
        self.client.get("/backend/v1/health")

    def test_unsigned_rejected(self):
        r = self.client.get("/backend/v1/queue")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"detail": "Unauthorized"})

    def test_signed_get_ok(self):
        r = self.client.get("/backend/v1/queue", headers=signed_headers("GET", "/backend/v1/queue"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("messages", r.json())

    def test_signed_with_query_ok(self):
        h = signed_headers("GET", "/backend/v1/config?probe=1")
        r = self.client.get("/backend/v1/config?probe=1", headers=h)
        self.assertEqual(r.status_code, 200)

    def test_query_not_covered_rejected(self):
        h = signed_headers("GET", "/backend/v1/config")
        r = self.client.get("/backend/v1/config?probe=1", headers=h)
        self.assertEqual(r.status_code, 401)

    def test_replay_rejected(self):
        h = signed_headers("GET", "/backend/v1/queue")
        self.assertEqual(self.client.get("/backend/v1/queue", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/backend/v1/queue", headers=h).status_code, 401)

    def test_stale_timestamp_rejected(self):
        h = signed_headers("GET", "/backend/v1/queue", ts=int(time.time()) - 600)
        self.assertEqual(self.client.get("/backend/v1/queue", headers=h).status_code, 401)

    def test_wrong_secret_rejected(self):
        h = signed_headers("GET", "/backend/v1/queue", secret="x" * 40)
        self.assertEqual(self.client.get("/backend/v1/queue", headers=h).status_code, 401)

    def test_previous_secret_accepted(self):
        h = signed_headers("GET", "/backend/v1/queue", secret=PREVIOUS)
        self.assertEqual(self.client.get("/backend/v1/queue", headers=h).status_code, 200)

    def test_tampered_body_rejected(self):
        body = b'{"event":"token","data":"hi"}'
        h = signed_headers("POST", "/backend/v1/stream/T-1/chunk", body)
        r = self.client.post("/backend/v1/stream/T-1/chunk", content=b'{"event":"token","data":"evil"}',
                             headers={**h, "content-type": "application/json"})
        self.assertEqual(r.status_code, 401)

    def test_signed_json_post_ok(self):
        body = b'{"event":"token","data":"hi"}'
        h = signed_headers("POST", "/backend/v1/stream/T-1/chunk", body)
        r = self.client.post("/backend/v1/stream/T-1/chunk", content=body,
                             headers={**h, "content-type": "application/json"})
        self.assertEqual(r.status_code, 200)

    def test_signed_multipart_post_ok(self):
        # Body is buffered by the middleware and replayed to the multipart parser.
        boundary = "testboundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\ncolor\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"clear\"\r\n\r\n1\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        h = signed_headers("POST", "/backend/v1/branding-logo", body)
        r = self.client.post("/backend/v1/branding-logo", content=body,
                             headers={**h, "content-type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(r.status_code, 200, r.text)

    def test_signed_before_start_rejected(self):
        h = signed_headers("GET", "/backend/v1/queue", ts=int(time.time()) - 30)  # inside the window
        self.assertEqual(self.client.get("/backend/v1/queue", headers=h).status_code, 401)


class PublicSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_browser_routes_work(self):
        self.assertEqual(self.client.get("/internal/config").status_code, 200)
        r = self.client.post("/internal/queue", json={
            "session_token": "AB12-CD34", "content": "hello", "message_id": "m1",
            "timestamp": "2026-10-30T00:00:00Z",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post("/internal/session/recover", json={"token": "AB12-CD34"}).status_code, 200)

    def test_backend_routes_absent_on_public_app(self):
        # Old backend-only routes are gone from the public surface
        for method, path in [
            ("GET", "/internal/queue"), ("GET", "/internal/uploads"),
            ("POST", "/internal/frontend-config"), ("POST", "/internal/branding"),
            ("POST", "/internal/branding-logo"), ("POST", "/internal/session/AB12-CD34/recovery-data"),
            ("POST", "/internal/stream/AB12-CD34/chunk"), ("POST", "/internal/auth/AB12-CD34/result"),
            ("GET", "/internal/upload/AB12-CD34/x.pdf"), ("DELETE", "/internal/upload/AB12-CD34/x.pdf"),
            ("GET", "/backend/v1/queue"), ("GET", "/backend/v1/config"),
        ]:
            r = self.client.request(method, path, json={} if method == "POST" else None)
            self.assertIn(r.status_code, (404, 405), f"{method} {path} -> {r.status_code}")


class ModeTest(unittest.TestCase):
    """Middleware configuration edge cases, on a minimal app."""

    def _client(self, **env):
        saved = {k: os.environ.get(k) for k in ("HRDD_BACKEND_SECRET", "HRDD_BACKEND_SECRET_PREVIOUS", "ALLOW_UNSIGNED_BACKEND_SURFACE")}
        try:
            for k in saved:
                os.environ.pop(k, None)
            os.environ.update(env)
            mini = FastAPI()
            mini.add_middleware(backend_auth.BackendSignatureMiddleware)

            @mini.post("/backend/v1/echo")
            async def echo(x: str = Form("")):
                return {"x": x}

            client = TestClient(mini)
            client.post("/backend/v1/echo")  # build the middleware with this env
            return client
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_no_secret_rejects_even_signed(self):
        c = self._client()
        self.assertEqual(c.post("/backend/v1/echo", headers=signed_headers("POST", "/backend/v1/echo")).status_code, 401)

    def test_short_secret_ignored(self):
        c = self._client(HRDD_BACKEND_SECRET="short")
        h = signed_headers("POST", "/backend/v1/echo", secret="short")
        self.assertEqual(c.post("/backend/v1/echo", headers=h).status_code, 401)

    def test_allow_unsigned_dev_switch(self):
        c = self._client(ALLOW_UNSIGNED_BACKEND_SURFACE="true")
        r = c.post("/backend/v1/echo", data={"x": "ok"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"x": "ok"})


if __name__ == "__main__":
    unittest.main()
