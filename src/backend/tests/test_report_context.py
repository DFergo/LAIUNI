"""Internal documents get the case material (survey, evidence) and the case file
classifies the facts against standards retrieved for them.

Runs the real path (polling._generate_internal_documents) against a fake
provider that records every request. Needs the backend image:
    docker run --rm -v "$PWD/src/backend:/app/src" -w /app ghcr.io/dfergo/laiuni-backend:latest \
        python -m unittest src.tests.test_report_context -v
"""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

import httpx  # noqa: E402

from src.services import llm_provider as lp  # noqa: E402
from src.services import polling, report_context, rag_service, evidence_processor  # noqa: E402
from src.services import prompt_assembler  # noqa: E402
from src.services.connection_registry import connections  # noqa: E402
from src.services.frontend_registry import registry  # noqa: E402
from src.api.v1.admin import llm as llm_admin  # noqa: E402
from src.core.paths import PROMPTS_DIR  # noqa: E402

FACTS_JSON = json.dumps({"context": "Germany, packaging, AcmePack, migrant workers",
                         "facts": ["Workers are made to work two unpaid hours after every shift.",
                                   "Workers who refuse overtime are threatened with dismissal."]})


def _sse(text: str) -> bytes:
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


class Fake:
    def __init__(self, facts_reply: str = FACTS_JSON):
        self.bodies: list[dict] = []
        self.facts_reply = facts_reply

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if "classification step" in body["messages"][0]["content"]:
            return httpx.Response(200, content=_sse(self.facts_reply))
        return httpx.Response(200, content=_sse("DOCUMENT TEXT"))

    def doc_bodies(self):
        return [b for b in self.bodies if "classification step" not in b["messages"][0]["content"]]


class ReportContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PROMPTS_DIR.exists():
            shutil.copytree(Path(__file__).parent.parent / "prompts", PROMPTS_DIR)
        if not connections.get("fake"):
            connections.add({"id": "fake", "type": "openai", "base_url": "http://fake/v1"})
        s = llm_admin._load_settings()
        s.update({"inference_connection": "fake", "inference_model": "m",
                  "reporter_connection": "fake", "reporter_model": "m", "inference_fallback_enabled": False})
        llm_admin._save_settings(s)

    def setUp(self):
        self.fid = registry.register(f"http://fe-{uuid.uuid4().hex[:6]}:8080", "t")["id"]
        self.token = f"CASE-{uuid.uuid4().hex[:4].upper()}"
        h = polling.history
        h.init_session(self.token, "CHAT SYSTEM PROMPT",
                       {"role": "worker", "type": "documentation", "company": "AcmePack",
                        "countryRegion": "Germany", "description": "Unpaid overtime"}, "en", "t", self.fid)
        h.add_message(self.token, "user", "We stay two hours after every shift without pay.")
        h.add_message(self.token, "assistant", "Thank you. How long has this been happening?")
        self._orig = {
            "httpx": lp.httpx.AsyncClient,
            "sources": rag_service.get_relevant_sources,
            "session_chunks": evidence_processor.get_session_rag_chunks,
            "evidence": evidence_processor.load_evidence_context,
        }
        rag_service.get_relevant_sources = lambda q, top_k=None, frontend_id=None: [
            {"text": "ILO C001 Art. 2: hours of work shall not exceed eight in the day.", "source": "ilo_c001.pdf", "scope": "global"},
            {"text": "Code of conduct §4: no forced or unpaid overtime.", "source": "acme_code.pdf", "scope": "campaign"},
        ]
        evidence_processor.get_session_rag_chunks = lambda token, q, top_k=3: ["Payslip: 40 h paid, 52 h worked."]
        evidence_processor.load_evidence_context = lambda token: [
            {"type": "text", "filename": "payslip.pdf", "summary": "Shows 52 hours worked, 40 paid."}]

    def tearDown(self):
        lp.httpx.AsyncClient = self._orig["httpx"]
        rag_service.get_relevant_sources = self._orig["sources"]
        evidence_processor.get_session_rag_chunks = self._orig["session_chunks"]
        evidence_processor.load_evidence_context = self._orig["evidence"]

    def _run(self, fake: Fake, mode: str = "documentation"):
        real = self._orig["httpx"]
        lp.httpx.AsyncClient = lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake.handler),
                                                       **{k: v for k, v in kw.items() if k != "transport"})
        asyncio.run(polling._generate_internal_documents(self.token, "en", mode, llm_admin._load_settings(), self.fid))

    def test_case_file_gets_case_data_and_classified_standards(self):
        fake = Fake()
        self._run(fake)
        docs = fake.doc_bodies()
        self.assertEqual(len(docs), 2)  # UNI summary + case file
        uni_sys, case_sys = docs[0]["messages"][0]["content"], docs[1]["messages"][0]["content"]
        for sys_text in (uni_sys, case_sys):
            self.assertIn("AcmePack", sys_text)            # survey
            self.assertIn("payslip.pdf", sys_text)         # evidence
            self.assertNotIn("CHAT SYSTEM PROMPT", sys_text)
            self.assertNotIn("{{module_", sys_text)        # module slots filled
        self.assertNotIn("Applicable standards", uni_sys)
        self.assertIn("Applicable standards", case_sys)
        self.assertIn("F1.", case_sys)
        self.assertIn("[P1] (source: ilo_c001.pdf)", case_sys)
        self.assertIn("[P2] (source: acme_code.pdf)", case_sys)
        self.assertIn("Payslip: 40 h paid", case_sys)      # user's own documents per fact
        self.assertIn("[P3]", docs[1]["messages"][-1]["content"])  # cite instruction

    def test_training_mode_has_no_case_file_and_no_fact_extraction(self):
        fake = Fake()
        self._run(fake, mode="training")
        self.assertEqual(len(fake.bodies), 1)              # UNI summary only

    def test_fact_extraction_failure_still_produces_the_case_file(self):
        fake = Fake(facts_reply="not json at all")
        self._run(fake)
        case_sys = fake.doc_bodies()[1]["messages"][0]["content"]
        self.assertIn("We stay two hours after every shift", case_sys)  # fallback: the user's messages as facts

    def test_per_frontend_custom_prompt_is_used(self):
        prompt_assembler.set_use_global(self.fid, False)
        custom_dir = prompt_assembler._frontend_prompts_dir(self.fid)
        custom_dir.mkdir(parents=True, exist_ok=True)
        (custom_dir / "internal_case_file.md").write_text("CUSTOM CASE FILE PROMPT FOR THIS FRONTEND")
        fake = Fake()
        self._run(fake)
        self.assertTrue(fake.doc_bodies()[1]["messages"][0]["content"].startswith("CUSTOM CASE FILE PROMPT"))


if __name__ == "__main__":
    unittest.main()
