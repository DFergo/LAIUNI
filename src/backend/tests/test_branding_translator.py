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


class PlaceholderTest(unittest.TestCase):
    """Sprint 43: texts are templates ({{org_name}}...). A translation must keep every placeholder."""

    def setUp(self):
        from src.services import llm_provider
        self.llm_provider = llm_provider
        self.replies: list[str] = []
        self.prompts: list[str] = []
        self._orig = (bt.llm.chat_with_fallback, llm_provider.build_fallback_chain)

        async def chat(messages, chain):
            self.prompts.append(messages[-1]["content"])
            return self.replies.pop(0)
        bt.llm.chat_with_fallback = chat
        llm_provider.build_fallback_chain = lambda settings, slot: []

    def tearDown(self):
        bt.llm.chat_with_fallback, self.llm_provider.build_fallback_chain = self._orig

    def translate(self, text):
        return asyncio.run(bt._translate_text(text, "Spanish", {}, "system"))

    def test_translation_with_placeholders_intact_is_kept(self):
        self.replies = ["Esta herramienta es de {{org_name}}."]
        self.assertEqual(self.translate("This tool is by {{org_name}}."), "Esta herramienta es de {{org_name}}.")
        self.assertIn("Keep every placeholder", self.prompts[0])

    def test_a_mangled_placeholder_is_retried_once(self):
        self.replies = ["Esta herramienta es de {{nombre_org}}.", "Esta herramienta es de {{ org_name }}."]
        self.assertEqual(self.translate("This tool is by {{org_name}}."), "Esta herramienta es de {{ org_name }}.")
        self.assertEqual(len(self.prompts), 2)

    def test_still_broken_after_the_retry_is_left_empty(self):
        self.replies = ["Sin marcador.", "Todavía sin marcador."]
        self.assertEqual(self.translate("This tool is by {{org_name}}."), "")

    def test_a_dropped_or_added_placeholder_does_not_pass(self):
        self.assertFalse(bt._keeps_placeholders("{{org_name}} and {{tool_name}}", "{{org_name}}"))
        self.assertFalse(bt._keeps_placeholders("{{org_name}}", "{{org_name}} {{org_name}}"))
        self.assertTrue(bt._keeps_placeholders("{{org_name}} y {{tool_name}}", "{{tool_name}} y {{org_name}}"))

    def test_text_without_placeholders_is_not_checked_or_retried(self):
        self.replies = ["Hola"]
        self.assertEqual(self.translate("Hello"), "Hola")
        self.assertNotIn("placeholder", self.prompts[0])


if __name__ == "__main__":
    unittest.main()
