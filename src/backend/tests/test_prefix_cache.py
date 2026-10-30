"""Prompt-cache acceptance (Sprint 37, handoff section A).

Drives real chat turns through ``polling._safe_process`` (the same path a user
message takes) against a fake OpenAI-compatible provider that records every
request body, then checks that turn N+1 starts with exactly the same bytes as
turn N — with evidence uploaded, per-turn RAG, and across a compression.

Needs the full backend dependencies, so run it in the backend image:
    docker run --rm -v "$PWD/src/backend:/app/src" -w /app ghcr.io/dfergo/laiuni-backend:latest \
        python -m unittest src.tests.test_prefix_cache -v
"""

import asyncio
import json
import os
import tempfile
import unittest

_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

import httpx  # noqa: E402

from src.services import llm_provider as lp  # noqa: E402
from src.services import polling  # noqa: E402
from src.services.connection_registry import connections  # noqa: E402
from src.api.v1.admin import llm as llm_admin  # noqa: E402

SUMMARY = "SUMMARY: the worker reported unpaid overtime at the plant."


def _sse(text: str) -> bytes:
    chunk = {"choices": [{"index": 0, "delta": {"content": text}}]}
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()


class FakeProvider:
    def __init__(self):
        self.inference_bodies: list[dict] = []
        self.turn = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        first = body["messages"][0]["content"]
        if isinstance(first, str) and "Summarize" in first or "compress" in str(first).lower():
            return httpx.Response(200, content=_sse(SUMMARY))
        self.inference_bodies.append(body)
        self.turn += 1
        return httpx.Response(200, content=_sse(f"Assistant reply {self.turn}."))


class PrefixCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil
        from pathlib import Path
        from src.core.paths import PROMPTS_DIR
        if not PROMPTS_DIR.exists():  # factory prompts, as on a fresh install
            shutil.copytree(Path(__file__).parent.parent / "prompts", PROMPTS_DIR)
        if not connections.get("fake"):
            connections.add({"id": "fake", "type": "openai", "base_url": "http://fake/v1"})

    def setUp(self):
        self.fake = FakeProvider()
        real = httpx.AsyncClient
        self._orig_llm = lp.httpx.AsyncClient
        lp.httpx.AsyncClient = lambda *a, **kw: real(
            *a, transport=httpx.MockTransport(self.fake.handler), **{k: v for k, v in kw.items() if k != "transport"})
        self._orig_fe = polling.frontend_client.AsyncClient
        polling.frontend_client.AsyncClient = lambda *a, **kw: real(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"})))
        self._patched = {
            "get_relevant_chunks": polling.get_relevant_chunks,
            "get_session_rag_chunks": polling.get_session_rag_chunks,
            "load_evidence_context": polling.load_evidence_context,
        }
        polling.get_relevant_chunks = lambda q, frontend_id=None: [f"Excerpt retrieved for: {q[:40]}"]
        polling.get_session_rag_chunks = lambda token, q: []
        polling.load_evidence_context = lambda token: [
            {"type": "text", "filename": "payslip.pdf", "summary": "Payslip shows 60 hours, paid 40."}]

    def tearDown(self):
        lp.httpx.AsyncClient = self._orig_llm
        polling.frontend_client.AsyncClient = self._orig_fe
        for name, fn in self._patched.items():
            setattr(polling, name, fn)

    def _settings(self, **extra):
        s = llm_admin._load_settings()
        s.update({"inference_connection": "fake", "inference_model": "m", "inference_fallback_enabled": False,
                  "summariser_connection": "fake", "summariser_model": "m", "summariser_enabled": False})
        s.update(extra)
        llm_admin._save_settings(s)

    def _turn(self, token: str, content: str, first: bool = False):
        msg = {"_frontend_url": "http://fe", "_frontend_id": "", "_frontend_name": "t",
               "session_token": token, "content": content, "language": "en"}
        if first:
            msg["survey"] = {"role": "worker", "type": "documentation", "language": "en"}
        asyncio.get_event_loop().run_until_complete(polling._safe_process(msg))

    @staticmethod
    def _common_prefix(a: list, b: list) -> int:
        n = 0
        for x, y in zip(a, b):
            if json.dumps(x, sort_keys=False) != json.dumps(y, sort_keys=False):
                break
            n += 1
        return n

    def test_turn_n_plus_1_starts_with_turn_n(self):
        self._settings()
        token = "PREF-0001"
        for i, text in enumerate(["I work at the plant.", "They do not pay overtime.", "It started in May."]):
            self._turn(token, text, first=(i == 0))
        bodies = self.fake.inference_bodies
        self.assertEqual(len(bodies), 3)
        for prev, nxt in zip(bodies, bodies[1:]):
            prev_msgs, next_msgs = prev["messages"], nxt["messages"]
            # Everything except this turn's user message (which carries the RAG tail) is identical.
            self.assertEqual(self._common_prefix(prev_msgs, next_msgs), len(prev_msgs) - 1)
            # And byte-identical as serialised in the request body.
            prefix = json.dumps(prev_msgs[:-1])[:-1]
            self.assertTrue(json.dumps(next_msgs).startswith(prefix))
        # Order: system prompt, evidence, then history; RAG only in the last user message.
        last = bodies[-1]["messages"]
        self.assertEqual([m["role"] for m in last[:2]], ["system", "system"])
        self.assertIn("payslip.pdf", last[1]["content"])
        self.assertIn("Reference excerpts", last[-1]["content"])
        self.assertTrue(all("Reference excerpts" not in str(m["content"]) for m in last[:-1]))

    def test_prefix_stable_after_compression(self):
        # Tiny thresholds so the 3rd turn compresses; the next turns must reuse the frozen summary.
        self._settings(summariser_enabled=True, compression_first_threshold=900,
                       compression_step_size=100000, inference_num_ctx=200000)
        token = "PREF-0002"
        long = "The supervisor said we must stay late. " * 25
        for i in range(6):
            self._turn(token, f"Turn {i}: {long}", first=(i == 0))
        bodies = self.fake.inference_bodies
        with_summary = [b for b in bodies if any(SUMMARY in str(m["content"]) for m in b["messages"])]
        self.assertGreaterEqual(len(with_summary), 2, "compression should have happened and persisted")
        for prev, nxt in zip(with_summary, with_summary[1:]):
            self.assertEqual(self._common_prefix(prev["messages"], nxt["messages"]), len(prev["messages"]) - 1)


if __name__ == "__main__":
    unittest.main()
