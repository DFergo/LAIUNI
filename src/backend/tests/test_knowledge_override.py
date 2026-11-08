"""Glossary and organizations: global on/off and per-frontend override.

Run in the backend image:
    docker run --rm -v "$PWD/src/backend:/app/src" -w /app ghcr.io/dfergo/laiuni-backend:latest \
        python -m unittest src.tests.test_knowledge_override -v
"""

import json
import os
import tempfile
import unittest

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.v1.admin import knowledge as kn  # noqa: E402
from src.api.v1.admin.auth import require_admin  # noqa: E402
from src.services import prompt_assembler  # noqa: E402
from src.services.frontend_registry import registry  # noqa: E402

GLOBAL_TERMS = [{"term": "Freedom of Association", "translations": {"es": "Libertad sindical"}},
                {"term": "Collective Bargaining", "translations": {"es": "Negociación colectiva"}}]
GLOBAL_ORGS = [{"name": "UNI Global Union", "type": "GUF", "country": "global"},
               {"name": "CCOO Servicios", "type": "union", "country": "Spain"}]
OWN_ORGS = [{"name": "SITRAMEX", "type": "union", "country": "Mexico"}]
OWN_TERMS = [{"term": "Protection contract", "translations": {"es": "Contrato de protección"}}]


class KnowledgeOverrideTest(unittest.TestCase):
    def setUp(self):
        kn._KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        (kn._KNOWLEDGE_DIR / "glossary.json").write_text(json.dumps({"terms": GLOBAL_TERMS}))
        (kn._KNOWLEDGE_DIR / "organizations.json").write_text(json.dumps({"organizations": GLOBAL_ORGS}))
        (kn._KNOWLEDGE_DIR / "settings.json").unlink(missing_ok=True)
        app = FastAPI()
        app.include_router(kn.router)
        app.dependency_overrides[require_admin] = lambda: {"admin": True}
        self.client = TestClient(app)
        self._orig_get = registry.get
        registry.get = lambda fid: {"id": fid} if fid.startswith("fe") else None
        self.fid = f"fe{self.id()[-6:]}"

    def tearDown(self):
        registry.get = self._orig_get

    def _prompt(self, fid, language="es"):
        return prompt_assembler._build_knowledge_section({"role": "worker"}, language, fid)

    def test_defaults_follow_the_global_lists(self):
        self.assertEqual(kn.effective_organizations(self.fid), GLOBAL_ORGS)
        self.assertEqual(kn.effective_glossary(self.fid), GLOBAL_TERMS)
        text = self._prompt(self.fid)
        self.assertIn("CCOO Servicios", text)
        self.assertIn("Libertad sindical", text)

    def test_escalation_path_names_the_organization_of_the_branding_tokens(self):
        from src.services import branding_tokens
        self.assertIn("national union → UNI Global Union.", self._prompt(self.fid))
        branding_tokens.save_global({"org_name": "Union X"})
        try:
            self.assertIn("national union → Union X.", self._prompt(self.fid))
        finally:
            branding_tokens.save_global({})

    def test_global_switches_off(self):
        r = self.client.put("/admin/knowledge/settings", json={"organizations_enabled": False})
        self.assertEqual(r.json(), {"glossary_enabled": True, "organizations_enabled": False})
        self.assertEqual(kn.effective_organizations(self.fid), [])
        self.assertEqual(kn.effective_organizations(), [])
        text = self._prompt(self.fid)
        self.assertNotIn("Organizations Reference", text)
        self.assertIn("Libertad sindical", text)                 # glossary still on

    def test_frontend_own_list_replaces_the_global_one(self):
        r = self.client.put(f"/admin/knowledge/frontend/{self.fid}/organizations",
                            json={"mode": "custom", "items": OWN_ORGS})
        self.assertEqual(r.status_code, 200)
        text = self._prompt(self.fid)
        self.assertIn("SITRAMEX", text)
        self.assertNotIn("CCOO Servicios", text)
        self.assertIn("CCOO Servicios", self._prompt("fe-other"))   # other frontends unchanged

    def test_own_list_applies_even_when_the_global_one_is_off(self):
        self.client.put("/admin/knowledge/settings", json={"glossary_enabled": False})
        self.client.put(f"/admin/knowledge/frontend/{self.fid}/glossary", json={"mode": "custom", "items": OWN_TERMS})
        self.assertIn("Contrato de protección", self._prompt(self.fid))
        self.assertNotIn("Terminology Reference", self._prompt("fe-other"))

    def test_frontend_off_and_back_to_global_keeps_its_list(self):
        url = f"/admin/knowledge/frontend/{self.fid}/organizations"
        self.client.put(url, json={"mode": "custom", "items": OWN_ORGS})
        self.client.put(url, json={"mode": "off"})
        self.assertNotIn("Organizations Reference", self._prompt(self.fid))
        state = self.client.get(f"/admin/knowledge/frontend/{self.fid}").json()
        self.assertEqual(state["organizations"], {"mode": "off", "organizations": OWN_ORGS})  # list kept
        self.client.put(url, json={"mode": "custom"})
        self.assertIn("SITRAMEX", self._prompt(self.fid))

    def test_validation(self):
        self.assertEqual(self.client.put(f"/admin/knowledge/frontend/{self.fid}/glossary",
                                         json={"mode": "sometimes"}).status_code, 400)
        self.assertEqual(self.client.put(f"/admin/knowledge/frontend/{self.fid}/other",
                                         json={"mode": "off"}).status_code, 404)
        self.assertEqual(self.client.get("/admin/knowledge/frontend/unknown").status_code, 404)

    def test_english_sessions_still_get_no_glossary(self):
        self.assertNotIn("Terminology Reference", self._prompt(self.fid, language="en"))


if __name__ == "__main__":
    unittest.main()
