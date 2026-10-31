"""Internal documents: case material (survey, evidence) and the case file
prepared in steps (analysis → research per fact → review → writing).

Runs the real path (polling._generate_internal_documents) against a fake
provider that answers per step and records every request. Needs the backend image:
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
from src.services import polling, rag_service, evidence_processor, case_file_pipeline  # noqa: E402
from src.services import prompt_assembler  # noqa: E402
from src.services.connection_registry import connections  # noqa: E402
from src.services.frontend_registry import registry  # noqa: E402
from src.api.v1.admin import llm as llm_admin  # noqa: E402
from src.core.paths import PROMPTS_DIR, SESSIONS_DIR  # noqa: E402

ILO = "ILO C001 Art. 2: The working hours of persons employed shall not exceed eight in the day."
CODE = "Code of conduct §4: no forced or unpaid overtime shall be required."
ANALYSIS = json.dumps({
    "context": {"country": "Germany", "sector": "packaging", "company": "AcmePack", "workers": "agency, migrant"},
    "parties": [{"name": "AcmePack", "role": "employer"}],
    "timeline": [{"when": "three months ago", "event": "unpaid overtime starts", "source": "user"}],
    "facts": [{"id": "F1", "statement": "Workers stay two unpaid hours after every shift.", "evidence": ["payslip"]},
              {"id": "F2", "statement": "Refusing overtime is threatened with non-renewal.", "evidence": []}],
    "gaps": ["Exact start date", "Number of workers affected"],
})
F1_FINAL = json.dumps({"classifications": [
    {"provision": "P1", "instrument": "ILO C001", "article": "Art. 2", "violation_type": "excessive hours",
     "strength": "clear", "quote": "shall not exceed eight in the day", "reasoning": "52 h weeks"},
    {"provision": "P2", "instrument": "Code of conduct", "article": "§4", "violation_type": "unpaid overtime",
     "strength": "clear", "quote": "words that are not in the provision", "reasoning": "x"}],
    "not_in_knowledge_base": [], "missing_information": ["timesheets"]})
F2_FINAL = json.dumps({"classifications": [
    {"provision": "P99", "instrument": "ILO C29", "article": "Art. 2", "violation_type": "forced labour",
     "strength": "probable", "quote": "menace of any penalty", "reasoning": "threat"}],
    "not_in_knowledge_base": [], "missing_information": []})
OLD_FACTS = json.dumps({"context": "Germany", "facts": ["Unpaid overtime.", "Threats of non-renewal."]})


def _sse(text: str) -> bytes:
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n".encode()


class Fake:
    def __init__(self, analysis_reply: str = ANALYSIS):
        self.bodies: list[dict] = []
        self.analysis_reply = analysis_reply
        self.research_calls: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        system, user = body["messages"][0]["content"], body["messages"][-1]["content"]
        if "analysis step of an internal" in system:
            return httpx.Response(200, content=_sse(self.analysis_reply))
        if "You classify one fact" in system:
            fid = "F1" if "# Fact F1" in user else "F2"
            n = self.research_calls[fid] = self.research_calls.get(fid, 0) + 1
            if fid == "F1" and n == 1:
                return httpx.Response(200, content=_sse(json.dumps({"more_searches": ["hours of work convention"]})))
            return httpx.Response(200, content=_sse(F1_FINAL if fid == "F1" else F2_FINAL))
        if "classification step" in system:
            return httpx.Response(200, content=_sse(OLD_FACTS))
        return httpx.Response(200, content=_sse("DOCUMENT TEXT"))

    def documents(self):
        return [b for b in self.bodies if b["messages"][0]["content"].startswith(("#", "CUSTOM"))
                and "analysis step" not in b["messages"][0]["content"]
                and "You classify one fact" not in b["messages"][0]["content"]
                and "classification step" not in b["messages"][0]["content"]]


class CaseFileTest(unittest.TestCase):
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
        (SESSIONS_DIR / self.token).mkdir(parents=True, exist_ok=True)
        self._orig = {
            "httpx": lp.httpx.AsyncClient,
            "sources": rag_service.get_relevant_sources,
            "session_chunks": evidence_processor.get_session_rag_chunks,
            "evidence": evidence_processor.load_evidence_context,
        }
        rag_service.get_relevant_sources = lambda q, top_k=None, frontend_id=None: (
            [{"text": ILO, "source": "ilo_c001.pdf", "scope": "global"},
             {"text": CODE, "source": "acme_code.pdf", "scope": "campaign"}]
            if "hours of work convention" not in q else
            [{"text": ILO, "source": "ilo_c001.pdf", "scope": "global"},
             {"text": "ILO C030 Art. 3: hours of work in commerce and offices.", "source": "ilo_c030.pdf", "scope": "global"}])
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

    def test_pipeline_prepares_and_reviews_the_case_file(self):
        fake = Fake()
        self._run(fake)
        docs = fake.documents()
        self.assertEqual(len(docs), 2)  # UNI summary + case file
        uni_sys, case_sys = docs[0]["messages"][0]["content"], docs[1]["messages"][0]["content"]
        for sys_text in (uni_sys, case_sys):
            self.assertIn("AcmePack", sys_text)            # survey
            self.assertIn("payslip.pdf", sys_text)         # evidence
            self.assertNotIn("{{module_", sys_text)
        self.assertNotIn("Case analysis", uni_sys)
        self.assertIn("## Chronology", case_sys)
        self.assertIn("three months ago — unpaid overtime starts", case_sys)
        self.assertIn("[P1] ILO C001 Art. 2 — excessive hours — strength: clear.", case_sys)       # verified quote
        self.assertIn("[P2] Code of conduct §4 — unpaid overtime — strength: possible — UNVERIFIED", case_sys)
        self.assertIn("(not in the knowledge base) ILO C29", case_sys)  # unknown ID P99 moved out
        self.assertIn("## Information gaps", case_sys)
        self.assertIn("[P1] (source: ilo_c001.pdf)", case_sys)          # only cited provisions listed
        self.assertNotIn("ilo_c030.pdf", case_sys)                      # retrieved but not cited
        self.assertIn("exactly the sections and headings of the template", docs[1]["messages"][-1]["content"])
        self.assertEqual(fake.research_calls, {"F1": 2, "F2": 1})       # F1 asked for one more search
        saved = json.loads((SESSIONS_DIR / self.token / "case_analysis.json").read_text())
        self.assertEqual(saved["stats"]["facts"], 2)
        self.assertEqual(saved["stats"]["verified"], 1)
        self.assertEqual(saved["research"][0]["searches"], ["hours of work convention"])

    def test_analysis_failure_falls_back_to_single_pass(self):
        fake = Fake(analysis_reply="not json")
        self._run(fake)
        case_sys = fake.documents()[1]["messages"][0]["content"]
        self.assertIn("Applicable standards (retrieved from the knowledge base for each fact)", case_sys)
        self.assertIn("Unpaid overtime.", case_sys)

    def test_training_mode_has_no_case_file_and_no_analysis(self):
        fake = Fake()
        self._run(fake, mode="training")
        self.assertEqual(len(fake.bodies), 1)              # UNI summary only

    def test_per_frontend_custom_prompt_is_used(self):
        prompt_assembler.set_use_global(self.fid, False)
        custom_dir = prompt_assembler._frontend_prompts_dir(self.fid)
        custom_dir.mkdir(parents=True, exist_ok=True)
        (custom_dir / "internal_case_file.md").write_text("CUSTOM CASE FILE PROMPT FOR THIS FRONTEND")
        fake = Fake()
        self._run(fake)
        self.assertTrue(any(b["messages"][0]["content"].startswith("CUSTOM CASE FILE PROMPT") for b in fake.bodies))


class LookupByNameTest(unittest.TestCase):
    """A standard listed as 'not in the knowledge base' is searched for by name;
    if that finds it, the fact is classified again with it."""

    def test_missing_standard_is_looked_up_and_reclassified(self):
        c29 = "ILO C029 Art. 2: forced labour means all work exacted under the menace of any penalty."
        calls = []

        def sources(q, top_k=None, frontend_id=None):
            if "C29" in q:
                return [{"text": c29, "source": "ilo_c029.pdf", "scope": "global"}]
            return [{"text": CODE, "source": "acme_code.pdf", "scope": "campaign"}]

        replies = [
            json.dumps({"classifications": [], "not_in_knowledge_base": [{"instrument": "ILO C29", "article": "Art. 2"}]}),
            json.dumps({"classifications": [{"provision": "P2", "instrument": "ILO C29", "article": "Art. 2",
                                              "violation_type": "forced labour", "strength": "probable",
                                              "quote": "under the menace of any penalty", "reasoning": "threat"}]}),
        ]

        async def ask(messages, settings, session):
            calls.append(messages[-1]["content"])
            return replies[len(calls) - 1]

        orig_sources, orig_ask, orig_chunks = rag_service.get_relevant_sources, case_file_pipeline._ask, evidence_processor.get_session_rag_chunks
        rag_service.get_relevant_sources, case_file_pipeline._ask = sources, ask
        evidence_processor.get_session_rag_chunks = lambda t, q, top_k=3: []
        try:
            cat = case_file_pipeline.Catalog()
            r = asyncio.run(case_file_pipeline.research_fact(
                {"id": "F1", "statement": "Threat of non-renewal for refusing overtime."}, "Germany", "T", "", {}, cat))
        finally:
            rag_service.get_relevant_sources, case_file_pipeline._ask = orig_sources, orig_ask
            evidence_processor.get_session_rag_chunks = orig_chunks
        self.assertEqual(len(calls), 2)
        self.assertIn("[P2] (source: ilo_c029.pdf)", calls[1])
        self.assertEqual(r["searches"], ["ILO C29 Art. 2"])
        self.assertEqual([(l["provision"], l["verified"]) for l in r["links"]], [("P2", True)])


class ReviewTest(unittest.TestCase):
    def test_quote_must_appear_in_provision(self):
        cat = case_file_pipeline.Catalog()
        pid = cat.add({"text": "Members shall suppress the use of forced labour.", "source": "c29", "scope": "global"})
        fact = {"id": "F1", "statement": "x"}
        ok = case_file_pipeline.review(fact, {"classifications": [
            {"provision": pid, "strength": "clear", "quote": "suppress the use of  forced labour"}]}, [pid], cat, [])
        bad = case_file_pipeline.review(fact, {"classifications": [
            {"provision": pid, "strength": "clear", "quote": "abolish child labour"}]}, [pid], cat, [])
        self.assertEqual((ok["links"][0]["strength"], ok["links"][0]["verified"]), ("clear", True))
        self.assertEqual((bad["links"][0]["strength"], bad["links"][0]["verified"]), ("possible", False))

    def test_provision_not_shown_to_this_fact_is_rejected(self):
        cat = case_file_pipeline.Catalog()
        p1 = cat.add({"text": "A", "source": "a", "scope": "global"})
        p2 = cat.add({"text": "B", "source": "b", "scope": "global"})
        r = case_file_pipeline.review({"id": "F1", "statement": "x"},
                                      {"classifications": [{"provision": p2, "quote": "B"}]}, [p1], cat, [])
        self.assertEqual(r["links"], [])
        self.assertEqual(len(r["not_in_knowledge_base"]), 1)


if __name__ == "__main__":
    unittest.main()
