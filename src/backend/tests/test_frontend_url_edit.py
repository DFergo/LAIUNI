"""Tests for editing a frontend's URL in place (PUT /admin/frontends/{id}).

The IP of an office DHCP frontend can rotate; editing the URL must preserve the
fid so campaign config under campaigns/{fid}/ survives (no delete + re-register).

Run inside the backend container:
    cd /app && python -m unittest src.tests.test_frontend_url_edit -v
"""

import asyncio
import os
import tempfile
import unittest

# Point DATA_DIR at a tmp dir BEFORE importing anything that reads paths, so the
# registry singleton loads from an empty tmp registry.
_TMP = tempfile.TemporaryDirectory()
os.environ["HRDD_DATA_DIR"] = _TMP.name

from fastapi import HTTPException  # noqa: E402

from src.services import frontend_registry as reg  # noqa: E402
from src.api.v1.admin import frontends as fe  # noqa: E402


class _FakeResp:
    def raise_for_status(self):
        return None


class _FakeClient:
    """Stand-in for httpx.AsyncClient — reachability controlled by a flag."""
    reachable = True

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        if not _FakeClient.reachable:
            raise RuntimeError("connection refused")
        return _FakeResp()


class FrontendUrlEditTest(unittest.TestCase):
    def setUp(self):
        # Fresh in-memory registry per test (tmp registry file starts empty).
        reg.registry._frontends = {}
        _FakeClient.reachable = True
        self._orig_client = fe.httpx.AsyncClient
        fe.httpx.AsyncClient = _FakeClient

    def tearDown(self):
        fe.httpx.AsyncClient = self._orig_client
        reg.registry._frontends = {}

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_edit_url_preserves_fid_and_config(self):
        f = reg.registry.register("http://10.210.66.130:8091", "M4-Tetra")
        fid = f["id"]
        # Seed distinctive campaign config
        reg.save_config(fid, {**reg.default_config(), "configured": True, "profiles": ["worker"]})

        res = self._run(fe.update_frontend(fid, fe.UpdateRequest(url="http://10.210.66.127:8091"), verify=True, _={}))

        self.assertEqual(res["frontend"]["id"], fid)  # fid unchanged
        self.assertEqual(res["frontend"]["url"], "http://10.210.66.127:8091")
        # Campaign config intact
        cfg = reg.load_config(fid)
        self.assertTrue(cfg["configured"])
        self.assertEqual(cfg["profiles"], ["worker"])

    def test_edit_url_normalises_trailing_slash(self):
        fid = reg.registry.register("http://a:8091", "A")["id"]
        res = self._run(fe.update_frontend(fid, fe.UpdateRequest(url="http://b:8091/"), verify=True, _={}))
        self.assertEqual(res["frontend"]["url"], "http://b:8091")

    def test_unreachable_url_rejected_400(self):
        fid = reg.registry.register("http://a:8091", "A")["id"]
        _FakeClient.reachable = False
        with self.assertRaises(HTTPException) as ctx:
            self._run(fe.update_frontend(fid, fe.UpdateRequest(url="http://dead:8091"), verify=True, _={}))
        self.assertEqual(ctx.exception.status_code, 400)
        # URL not changed on failure
        self.assertEqual(reg.registry.get(fid)["url"], "http://a:8091")

    def test_verify_false_skips_reachability(self):
        fid = reg.registry.register("http://a:8091", "A")["id"]
        _FakeClient.reachable = False  # would 400 if verified
        res = self._run(fe.update_frontend(fid, fe.UpdateRequest(url="http://mini.local:8091"), verify=False, _={}))
        self.assertEqual(res["frontend"]["url"], "http://mini.local:8091")

    def test_collision_rejected_409(self):
        a = reg.registry.register("http://a:8091", "A")["id"]
        reg.registry.register("http://b:8091", "B")
        with self.assertRaises(HTTPException) as ctx:
            self._run(fe.update_frontend(a, fe.UpdateRequest(url="http://b:8091"), verify=True, _={}))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_collision_checked_even_when_verify_false(self):
        a = reg.registry.register("http://a:8091", "A")["id"]
        reg.registry.register("http://b:8091", "B")
        with self.assertRaises(HTTPException) as ctx:
            self._run(fe.update_frontend(a, fe.UpdateRequest(url="http://b:8091"), verify=False, _={}))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_name_only_update_still_works(self):
        fid = reg.registry.register("http://a:8091", "old")["id"]
        res = self._run(fe.update_frontend(fid, fe.UpdateRequest(name="new"), verify=True, _={}))
        self.assertEqual(res["frontend"]["name"], "new")
        self.assertEqual(res["frontend"]["url"], "http://a:8091")


if __name__ == "__main__":
    unittest.main()
