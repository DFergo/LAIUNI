"""Sprint 43 — the branding API (global + per-frontend), what is pushed to a frontend, and the emails.

Run inside the backend container:
    cd /app && python -m unittest src.tests.test_branding_api -v
"""

import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

# polling pulls in the LLM/RAG stack; the API only needs its cache-invalidation hook.
CACHE_CLEARED: list[str] = []
_polling = types.ModuleType("src.services.polling")
_polling.invalidate_branding_cache = lambda fid="": CACHE_CLEARED.append(fid)
sys.modules["src.services.polling"] = _polling

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from src.api.v1.admin import frontends as fe  # noqa: E402
from src.api.v1.admin.auth import require_admin  # noqa: E402
from src.api.v1.admin.branding import router as branding_router  # noqa: E402
from src.services import branding_push, branding_tokens as bt, smtp_service  # noqa: E402
import src.services.branding_translator as translator  # noqa: E402


def png(transparent: bool = True) -> bytes:
    img = Image.new("RGBA", (40, 20), (0, 0, 0, 0) if transparent else (200, 30, 30, 255))
    if transparent:
        for x in range(10, 30):
            for y in range(5, 15):
                img.putpixel((x, y), (200, 30, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class BrandingApiTest(unittest.TestCase):
    def setUp(self):
        fe._CAMPAIGNS_DIR = Path(_TMP.name) / "campaigns"
        translator._CAMPAIGNS_DIR = fe._CAMPAIGNS_DIR
        for p in Path(_TMP.name).iterdir():
            import shutil
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        CACHE_CLEARED.clear()
        app = FastAPI()
        app.include_router(branding_router)
        app.include_router(fe.router)
        app.dependency_overrides[require_admin] = lambda: {}
        self.client = TestClient(app)
        self.anon = FastAPI()
        self.anon.include_router(branding_router)
        self.anon_client = TestClient(self.anon)

    # ------------------------------------------------------------ global

    def test_public_endpoint_needs_no_login_and_the_rest_does(self):
        r = self.anon_client.get("/admin/branding/public")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["color_primary"], "#003087")
        self.assertNotIn("logos", r.json())
        self.assertIn(self.anon_client.get("/admin/branding").status_code, (401, 403))

    def test_change_global_tokens_and_reset_one(self):
        r = self.client.put("/admin/branding", json={"values": {"org_name": "Union A", "color_primary": "#0a7f3c"}})
        self.assertEqual(r.status_code, 200, r.text)
        tokens = {t["name"]: t for t in r.json()["tokens"]}
        self.assertEqual((tokens["org_name"]["value"], tokens["org_name"]["source"]), ("Union A", "global"))
        self.assertEqual(tokens["color_primary"]["value"], "#0A7F3C")
        self.assertEqual(CACHE_CLEARED, [""])                                   # every frontend is re-pushed
        r = self.client.put("/admin/branding", json={"values": {"org_name": ""}})
        tokens = {t["name"]: t for t in r.json()["tokens"]}
        self.assertEqual(tokens["org_name"]["source"], "default")
        self.assertEqual(tokens["color_primary"]["source"], "global")           # untouched

    def test_bad_values_are_refused_and_nothing_is_saved(self):
        for values in ({"color_primary": "green"}, {"copyright_holder": "X"}, {"nope": "x"}):
            r = self.client.put("/admin/branding", json={"values": values})
            self.assertEqual(r.status_code, 400, values)
        self.assertEqual(bt.global_overrides(), {})

    def test_contrast_warning_is_reported(self):
        r = self.client.put("/admin/branding", json={"values": {"color_primary": "#FFE066"}})
        self.assertTrue(r.json()["warnings"])
        r = self.client.put("/admin/branding", json={"values": {"color_on_primary": "#000000"}})
        self.assertEqual(r.json()["warnings"], [])

    def test_logo_upload_preview_and_delete(self):
        r = self.client.post("/admin/branding/logo/header", files={"file": ("logo.png", png(), "image/png")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["logos"]["header"], {**r.json()["logos"]["header"], "uploaded": True, "has_white": True,
                                                       "source": "global"})
        self.assertEqual(self.client.get("/admin/branding/logo/header/white").status_code, 200)
        self.assertEqual(self.client.get("/admin/branding/logo/page/color").status_code, 404)
        flat = self.client.post("/admin/branding/logo/chat_bg", files={"file": ("l.png", png(False), "image/png")})
        self.assertFalse(flat.json()["logos"]["chat_bg"]["has_white"])           # no transparency, no white variant
        self.assertEqual(self.client.delete("/admin/branding/logo/header").json()["logos"]["header"]["uploaded"], False)

    def test_logo_upload_refuses_unknown_slot_and_format(self):
        self.assertEqual(self.client.post("/admin/branding/logo/footer",
                                          files={"file": ("l.png", png(), "image/png")}).status_code, 404)
        self.assertEqual(self.client.post("/admin/branding/logo/header",
                                          files={"file": ("l.svg", b"<svg/>", "image/svg+xml")}).status_code, 400)

    def test_reset_returns_to_the_defaults(self):
        self.client.put("/admin/branding", json={"values": {"org_name": "Union A"}})
        self.client.post("/admin/branding/logo/header", files={"file": ("l.png", png(), "image/png")})
        r = self.client.post("/admin/branding/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(t["source"] == "default" for t in r.json()["tokens"]))
        self.assertFalse(any(l["uploaded"] for l in r.json()["logos"].values()))

    # ------------------------------------------------------------ per frontend

    def branding(self, fid="fe1", **extra):
        return {"app_title": "", "logo_url": "", "logo_mode": "white", "disclaimer_text": "",
                "instructions_text": "", **extra}

    def test_frontend_inherits_overrides_and_goes_back(self):
        self.client.put("/admin/branding", json={"values": {"org_name": "Union A"}})
        r = self.client.put("/admin/frontends/fe1/branding", json=self.branding(tokens={"color_primary": "#112233"}))
        self.assertEqual(r.status_code, 200, r.text)
        cat = {t["name"]: t for t in self.client.get("/admin/frontends/fe1/branding").json()["catalog"]["tokens"]}
        self.assertEqual((cat["org_name"]["value"], cat["org_name"]["source"]), ("Union A", "global"))
        self.assertEqual((cat["color_primary"]["value"], cat["color_primary"]["source"]), ("#112233", "frontend"))
        # saving without `tokens` (an older client) keeps the overrides
        self.client.put("/admin/frontends/fe1/branding", json=self.branding())
        self.assertEqual(bt.frontend_overrides("fe1"), {"color_primary": "#112233"})
        # an empty value removes one override
        self.client.put("/admin/frontends/fe1/branding", json=self.branding(tokens={"color_primary": ""}))
        self.assertEqual(bt.frontend_overrides("fe1"), {})

    def test_frontend_tokens_are_validated(self):
        r = self.client.put("/admin/frontends/fe1/branding", json=self.branding(tokens={"color_primary": "red"}))
        self.assertEqual(r.status_code, 400)

    def test_frontend_logo_slots_inherit_the_global_logo(self):
        self.client.post("/admin/branding/logo/chat_bg", files={"file": ("l.png", png(), "image/png")})
        r = self.client.get("/admin/frontends/fe1/branding")
        self.assertEqual(r.json()["catalog"]["logos"]["chat_bg"]["source"], "global")
        r = self.client.post("/admin/frontends/fe1/branding/logo/chat_bg", files={"file": ("l.png", png(False), "image/png")})
        self.assertEqual(r.json()["logos"]["chat_bg"]["source"], "frontend")
        self.assertEqual(self.client.get("/admin/frontends/fe1/branding/logo/chat_bg/color").status_code, 200)
        r = self.client.delete("/admin/frontends/fe1/branding/logo/chat_bg")
        self.assertEqual(r.json()["logos"]["chat_bg"]["source"], "global")

    # ------------------------------------------------------------ what the frontend receives, and emails

    def test_payload_carries_resolved_tokens_and_logo_state(self):
        self.client.put("/admin/branding", json={"values": {"tool_name": "Rights Desk", "org_name": "Union A"}})
        self.client.put("/admin/frontends/fe1/branding", json=self.branding(
            disclaimer_text="By {{org_name}}", tokens={"org_name": "Campaign X"}))
        p = branding_push.build_payload("fe1")
        self.assertEqual(p["tokens"]["org_name"], "Campaign X")
        self.assertEqual(p["tokens"]["tool_name"], "Rights Desk")
        self.assertEqual(p["app_title"], "Rights Desk")
        self.assertTrue(p["custom"])
        self.assertEqual(p["disclaimer_text"], "By {{org_name}}")                # the template, resolved when shown
        self.assertEqual(set(p["logos"]), {"header", "page", "chat_bg"})
        plain = branding_push.build_payload("nobranding")                         # a frontend with no branding file
        self.assertEqual(plain["tokens"]["org_name"], "Union A")
        self.assertFalse(plain["custom"])

    def test_role_only_instructions_count_as_custom(self):
        self.client.put("/admin/frontends/fe1/branding", json=self.branding(instructions_text_worker="Hello"))
        self.assertTrue(branding_push.build_payload("fe1")["custom"])

    def test_emails_use_the_tool_name(self):
        self.client.put("/admin/branding", json={"values": {"tool_name": "Rights Desk"}})
        self.assertEqual(smtp_service._tool(), "Rights Desk")
        self.client.put("/admin/frontends/fe1/branding", json=self.branding(app_title="Campaign Desk"))
        self.assertEqual(smtp_service._tool("fe1"), "Campaign Desk")
        self.assertEqual(smtp_service._tool("other"), "Rights Desk")

    def test_legacy_title_still_shows_and_old_single_logo_keeps_working(self):
        d = fe._CAMPAIGNS_DIR / "old"
        d.mkdir(parents=True)
        (d / "branding.json").write_text(json.dumps({"app_title": "Old Title", "logo_uploaded": True}))
        (d / "logo_color.png").write_bytes(png())
        p = branding_push.build_payload("old")
        self.assertEqual(p["app_title"], "Old Title")
        self.assertTrue(p["logos"]["header"]["uploaded"] and p["logos"]["page"]["uploaded"])
        self.assertFalse(p["logos"]["chat_bg"]["uploaded"])


if __name__ == "__main__":
    unittest.main()
