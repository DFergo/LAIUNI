"""Tests for the LLM adapters against recorded/representative provider streams.

Run inside the backend container:
    cd /app && python -m unittest src.tests.test_llm_provider -v
"""

import asyncio
import unittest
from pathlib import Path

import httpx

from src.services import llm_provider as lp

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FixtureTransport:
    """Patches httpx.AsyncClient in llm_provider to replay a fixture and record the request."""

    def __init__(self, fixture: str, status: int = 200):
        self.body = (FIXTURES / fixture).read_bytes() if fixture else b""
        self.status = status
        self.requests: list[httpx.Request] = []

    def __enter__(self):
        self._orig = lp.httpx.AsyncClient
        real = self._orig

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status, content=self.body,
                                  headers={"content-type": "text/event-stream"})

        def factory(*a, **kw):
            kw.pop("transport", None)
            return real(*a, transport=httpx.MockTransport(handler), **kw)

        lp.httpx.AsyncClient = factory
        return self

    def __exit__(self, *a):
        lp.httpx.AsyncClient = self._orig


async def _collect(adapter, conn, model, **kw):
    out = []
    async for tok in adapter.stream(conn, model, [{"role": "user", "content": "hi"}],
                                    kw.get("temperature"), kw.get("max_tokens"), kw.get("num_ctx")):
        out.append(tok)
    return out


class ContentNormaliserTest(unittest.TestCase):
    def test_string(self):
        self.assertEqual(lp._content_text("abc"), "abc")

    def test_none_and_junk(self):
        self.assertEqual(lp._content_text(None), "")
        self.assertEqual(lp._content_text(42), "")

    def test_blocks_keep_text_drop_thinking(self):
        blocks = [{"type": "thinking", "thinking": [{"type": "text", "text": "secret"}]},
                  {"type": "text", "text": "Hello"}, {"type": "text", "text": " world"}]
        self.assertEqual(lp._content_text(blocks), "Hello world")

    def test_single_block_dict(self):
        self.assertEqual(lp._content_text({"type": "text", "text": "x"}), "x")


class OpenAIStreamTest(unittest.TestCase):
    CONN = {"id": "c", "type": "openai", "base_url": "https://api.example/v1", "api_key": "k"}

    def test_mistral_block_stream_yields_only_text(self):
        with _FixtureTransport("mistral_large4_stream.sse"):
            toks = _run(_collect(lp.OpenAIAdapter(), self.CONN, "mistral-large-4"))
        self.assertTrue(all(isinstance(t, str) for t in toks))
        self.assertEqual("".join(toks), "Hello, how can I help?")
        self.assertNotIn("user greets", "".join(toks))

    def test_openrouter_reasoning_field_ignored_and_usage_chunk_tolerated(self):
        with _FixtureTransport("openrouter_qwen_stream.sse"):
            toks = _run(_collect(lp.OpenAIAdapter(), self.CONN, "qwen/qwen3.8-flash"))
        self.assertEqual("".join(toks), "Yes.")


if __name__ == "__main__":
    unittest.main()
