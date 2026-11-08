"""Sprint 43 — the sidecar stores and serves the branding tokens and the three logo slots.

Run inside the frontend container (or any Python 3.11 env with the sidecar deps + httpx):
    cd /app && python -m unittest sidecar.tests.test_branding -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from sidecar import main as sidecar
from sidecar.tests.test_backend_surface import signed_headers


def multipart(fields: dict[str, str], files: dict[str, bytes] | None = None) -> tuple[bytes, str]:
    boundary = "b0undary"
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, v in (files or {}).items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{k}.png"\r\n'
                f"Content-Type: image/png\r\n\r\n").encode() + v + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class SidecarBrandingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (sidecar._BRANDING_DIR, sidecar._TOKENS_FILE, sidecar._tokens, sidecar._branding,
                      sidecar._branding_translations)
        sidecar._BRANDING_DIR = Path(self.tmp.name)
        sidecar._TOKENS_FILE = Path(self.tmp.name) / "tokens.json"
        sidecar._tokens, sidecar._branding, sidecar._branding_translations = {}, {}, {}
        sidecar.backend_app.middleware_stack = None
        self.backend = TestClient(sidecar.backend_app)
        self.backend.get("/backend/v1/health")
        self.public = TestClient(sidecar.app)

    def tearDown(self):
        (sidecar._BRANDING_DIR, sidecar._TOKENS_FILE, sidecar._tokens, sidecar._branding,
         sidecar._branding_translations) = self.saved
        self.tmp.cleanup()

    def push_json(self, path, payload):
        body = json.dumps(payload).encode()
        h = signed_headers("POST", path, body)
        r = self.backend.post(path, content=body, headers={**h, "content-type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)

    def push_logo(self, fields, files=None):
        body, ctype = multipart(fields, files)
        h = signed_headers("POST", "/backend/v1/branding-logo", body)
        r = self.backend.post("/backend/v1/branding-logo", content=body, headers={**h, "content-type": ctype})
        self.assertEqual(r.status_code, 200, r.text)

    def test_tokens_are_kept_even_without_custom_text(self):
        self.push_json("/backend/v1/branding", {"custom": False, "app_title": "Our Tool", "translations": None,
                                                "logos": {"header": {}},
                                                "tokens": {"org_name": "Union A", "color_primary": "#112233"}})
        cfg = self.public.get("/internal/config").json()
        self.assertEqual(cfg["branding"]["tokens"]["org_name"], "Union A")
        self.assertEqual(cfg["branding"]["tokens"]["color_primary"], "#112233")
        self.assertTrue((Path(self.tmp.name) / "tokens.json").exists())
        self.assertFalse((Path(self.tmp.name) / "config.json").exists())

    def test_each_slot_is_stored_and_served_on_its_own(self):
        self.push_logo({"slot": "chat_bg", "mode": "white"}, {"color": b"BG"})
        self.assertEqual(self.public.get("/internal/branding-logo/chat_bg/color").content, b"BG")
        self.assertEqual(self.public.get("/internal/branding-logo/header/color").status_code, 404)
        logos = self.public.get("/internal/config").json()["branding"]["logos"]
        self.assertEqual(logos["chat_bg"], {"uploaded": True, "has_white": False})
        self.assertEqual(logos["header"], {"uploaded": False, "has_white": False})
        self.push_logo({"slot": "chat_bg", "clear": "1"})
        self.assertEqual(self.public.get("/internal/branding-logo/chat_bg/color").status_code, 404)

    def test_unknown_slot_refused(self):
        body, ctype = multipart({"slot": "../etc", "mode": "white"}, {"color": b"x"})
        h = signed_headers("POST", "/backend/v1/branding-logo", body)
        r = self.backend.post("/backend/v1/branding-logo", content=body, headers={**h, "content-type": ctype})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.public.get("/internal/branding-logo/..%2Fetc/color").status_code, 404)

    def test_push_without_slot_from_an_older_backend_serves_header_and_pages(self):
        self.push_logo({"mode": "white"}, {"color": b"OLD", "white": b"OLDW"})
        for slot in ("header", "page"):
            self.assertEqual(self.public.get(f"/internal/branding-logo/{slot}/color").content, b"OLD")
        self.assertEqual(self.public.get("/internal/branding-logo/white").content, b"OLDW")     # route kept
        self.assertEqual(self.public.get("/internal/branding-logo/chat_bg/color").status_code, 404)

    def test_logo_left_by_a_sidecar_from_before_slots_still_shows(self):
        (Path(self.tmp.name) / "logo_color.png").write_bytes(b"LEGACY")
        self.assertEqual(self.public.get("/internal/branding-logo/header/color").content, b"LEGACY")
        self.assertEqual(self.public.get("/internal/branding-logo/color").content, b"LEGACY")


if __name__ == "__main__":
    unittest.main()
