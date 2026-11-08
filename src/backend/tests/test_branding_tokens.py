"""Sprint 43 — branding tokens: validation, inheritance, logos, contrast, and that the
frontend's built-in defaults match the catalog.

    python -m unittest src.tests.test_branding_tokens   (inside the backend image)
"""

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

from src.services import branding_tokens as bt  # noqa: E402


class BrandingTokensTest(unittest.TestCase):
    def setUp(self):
        for p in Path(_TMP.name).iterdir():
            shutil.rmtree(p) if p.is_dir() else p.unlink()

    def test_defaults_are_the_uni_look(self):
        v = bt.values()
        self.assertEqual(v["org_name"], "UNI Global Union")
        self.assertEqual(v["color_primary"], "#003087")
        self.assertEqual(v["color_on_primary"], "#FFFFFF")

    def test_validation(self):
        self.assertEqual(bt.validate({"color_primary": "#0a7f3c"}), {"color_primary": "#0A7F3C"})
        for bad in ({"color_primary": "blue"}, {"color_primary": "#12345"}, {"nope": "x"},
                    {"copyright_holder": "Other"}, {"org_name": "x" * 500}, {"tool_name": "a\nb"},
                    {"tool_name": "{{org_name}}"}, {"org_name": 5}):
            with self.assertRaises(bt.TokenError, msg=str(bad)):
                bt.validate(bad)
        self.assertEqual(bt.validate({"org_name": "  ", "tool_name": None}), {})   # empty = unset

    def test_frontend_overrides_global_overrides_default(self):
        bt.save_global({"org_name": "Union A", "color_primary": "#112233"})
        bt.save_frontend_overrides("fe1", {"org_name": "Campaign X"})
        r = bt.resolve("fe1")
        self.assertEqual((r["org_name"]["value"], r["org_name"]["source"]), ("Campaign X", "frontend"))
        self.assertEqual((r["color_primary"]["value"], r["color_primary"]["source"]), ("#112233", "global"))
        self.assertEqual(r["tool_name"]["source"], "default")
        bt.save_global({"org_name": "Union B"})                     # a global change reaches frontends that inherit
        self.assertEqual(bt.values("fe2")["org_name"], "Union B")
        self.assertEqual(bt.values("fe1")["org_name"], "Campaign X")

    def test_legacy_app_title_is_the_frontends_tool_name(self):
        d = Path(_TMP.name) / "campaigns" / "old"
        d.mkdir(parents=True)
        (d / "branding.json").write_text('{"app_title": "Old Title", "disclaimer_text": "kept"}')
        self.assertEqual(bt.values("old")["tool_name"], "Old Title")
        bt.save_frontend_overrides("old", {"org_name": "X"})         # other fields survive
        self.assertIn("kept", (d / "branding.json").read_text())

    def test_render_replaces_known_tokens_only(self):
        vals = {"org_name": "Union A", "tool_name": "Helper"}
        self.assertEqual(bt.render("By {{org_name}} — {{ tool_name }} {{unknown}}", vals),
                         "By Union A — Helper {{unknown}}")

    def test_contrast_warning_for_unreadable_pair(self):
        ok = bt.contrast_warnings(bt.DEFAULTS)
        self.assertEqual(ok, [])
        bad = bt.contrast_warnings({**bt.DEFAULTS, "color_primary": "#FFE066"})
        self.assertTrue(any("primary" in w for w in bad))
        self.assertEqual(bt.contrast_warnings({**bt.DEFAULTS, "color_primary": "#FFE066", "color_on_primary": "#000000"}), [])

    def test_logo_inheritance(self):
        self.assertEqual(bt.effective_logo("fe1", "header")["source"], "none")
        bt.save_logo(None, "header", b"G", b"GW")
        self.assertEqual(bt.effective_logo("fe1", "header")["source"], "global")
        bt.save_logo("fe1", "header", b"F", None)
        eff = bt.effective_logo("fe1", "header")
        self.assertEqual((eff["source"], eff["white"]), ("frontend", None))
        self.assertEqual(bt.effective_logo("fe1", "page")["source"], "none")        # slots are independent
        bt.delete_logo("fe1", "header")
        self.assertEqual(bt.effective_logo("fe1", "header")["source"], "global")

    def test_legacy_single_logo_serves_header_and_page_only(self):
        d = Path(_TMP.name) / "campaigns" / "old"
        d.mkdir(parents=True)
        (d / "logo_color.png").write_bytes(b"C")
        (d / "logo_white.png").write_bytes(b"W")
        self.assertEqual(bt.effective_logo("old", "header")["source"], "frontend")
        self.assertEqual(bt.effective_logo("old", "page")["source"], "frontend")
        self.assertEqual(bt.effective_logo("old", "chat_bg")["source"], "none")
        bt.delete_logo("old", "header")
        self.assertFalse((d / "logo_color.png").exists())

    def test_logo_url_beats_the_global_logo_on_header_and_pages(self):
        bt.save_logo(None, "header", b"G", None)
        bt.save_logo(None, "chat_bg", b"G", None)
        d = Path(_TMP.name) / "campaigns" / "u"
        d.mkdir(parents=True)
        (d / "branding.json").write_text('{"logo_url": "https://x/logo.png"}')
        self.assertEqual(bt.effective_logo("u", "header")["source"], "none")
        self.assertEqual(bt.effective_logo("u", "chat_bg")["source"], "global")

    def test_catalog_lists_tokens_logos_and_the_fixed_copyright(self):
        c = bt.catalog()
        self.assertEqual([t["name"] for t in c["tokens"]], list(bt.DEFAULTS))
        self.assertEqual(set(c["logos"]), {"header", "page", "chat_bg"})
        self.assertEqual(c["fixed"][0]["name"], "copyright_holder")

    def test_catalog_says_what_a_cleared_token_falls_back_to(self):
        bt.save_global({"org_name": "Union A"})
        bt.save_frontend_overrides("fe1", {"org_name": "Campaign X"})
        own = {t["name"]: t for t in bt.catalog("fe1")["tokens"]}
        self.assertEqual((own["org_name"]["value"], own["org_name"]["inherited"]), ("Campaign X", "Union A"))
        glob = {t["name"]: t for t in bt.catalog()["tokens"]}
        self.assertEqual((glob["org_name"]["value"], glob["org_name"]["inherited"]), ("Union A", "UNI Global Union"))

    def test_frontend_builtin_defaults_match_the_catalog(self):
        """frontend/src/branding.ts keeps a copy of the defaults for the moments before the backend pushes."""
        ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "branding.ts"
        if not ts.exists():
            self.skipTest("frontend source not mounted")
        found = dict(re.findall(r"^\s+(\w+): '([^']*)',?\s*$", ts.read_text(), re.M))
        for name, default in bt.DEFAULTS.items():
            self.assertEqual(found.get(name, "").upper(), default.upper(), name)


if __name__ == "__main__":
    unittest.main()
