"""Branding is translated only into the frontend's configured languages.

Run inside the backend container:
    cd /app && python -m unittest src.tests.test_branding_translator -v
"""

import asyncio
import os
import tempfile
import unittest

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

from src.services import branding_translator as bt  # noqa: E402
from src.services import frontend_registry as reg  # noqa: E402


class BrandingLanguagesTest(unittest.TestCase):
    def setUp(self):
        self.calls: list[str] = []
        self._orig = bt._translate_text

        async def fake(text, lang_name, settings, system_prompt):
            self.calls.append(lang_name)
            return f"[{lang_name}] {text}"
        bt._translate_text = fake
        import uuid
        self.fid = reg.registry.register(f"http://fe-{uuid.uuid4().hex[:8]}:8080", "t")["id"]

    def tearDown(self):
        bt._translate_text = self._orig

    def _translate(self):
        asyncio.run(bt.translate_branding(self.fid, {"disclaimer_text": "Hello"}))

    def test_only_configured_languages(self):
        reg.save_config(self.fid, {**reg.default_config(), "languages": ["es", "fr"]})
        self._translate()
        self.assertEqual(sorted(self.calls), ["French", "Spanish"])
        saved = bt.load_translations(self.fid)
        self.assertEqual(saved["en"]["disclaimer_text"], "Hello")  # source always present
        self.assertNotIn("de", saved)

    def test_enabling_a_language_translates_only_that_one(self):
        reg.save_config(self.fid, {**reg.default_config(), "languages": ["es"]})
        self._translate()
        self.calls.clear()
        reg.save_config(self.fid, {**reg.default_config(), "languages": ["es", "de"]})
        self._translate()
        self.assertEqual(self.calls, ["German"])

    def test_no_languages_configured_means_all(self):
        reg.save_config(self.fid, {**reg.default_config(), "languages": []})
        self._translate()
        self.assertEqual(len(self.calls), len(bt.LANGUAGES) - 1)  # all but the English source


if __name__ == "__main__":
    unittest.main()
