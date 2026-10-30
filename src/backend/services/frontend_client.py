"""HTTP client for backend → frontend calls (signed backend surface).

Every frontend in the registry may carry:
  - `signing_secret`: HMAC secret shared with that frontend (HRDD_BACKEND_SECRET there)
  - `extra_headers`:  optional headers sent on every request (e.g. Cloudflare Access
                      service-token `CF-Access-Client-Id` / `CF-Access-Client-Secret`)

With a secret, call sites keep writing `{url}/internal/<op>` and this client
rewrites it to `{url}/backend/v1/<op>` and signs it (the registered URL is the
frontend's backend port). Without a secret the request goes out unchanged to
the legacy unsigned routes — transition mode for frontends registered before
signing existed; a warning is logged once per frontend.

Canonical string (must match src/frontend/sidecar/backend_auth.py):
    v1\\n{ts}\\n{nonce}\\n{METHOD}\\n{path?query}\\n{sha256hex(body)}
"""

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any

import httpx

logger = logging.getLogger("backend.frontend_client")

LEGACY_PREFIX = "/internal/"
SIGNED_PREFIX = "/backend/v1/"

_warned_unsigned: set[str] = set()


def sign(secret: str, ts: str, nonce: str, method: str, path_qs: str, body: bytes) -> str:
    canon = "\n".join(["v1", ts, nonce, method.upper(), path_qs, hashlib.sha256(body).hexdigest()])
    return "v1=" + hmac.new(secret.encode(), canon.encode(), hashlib.sha256).hexdigest()


def _sign_request(request: httpx.Request, secret: str, extra_headers: dict[str, str] | None):
    path = request.url.path
    if path.startswith(LEGACY_PREFIX):
        request.url = request.url.copy_with(path=SIGNED_PREFIX + path[len(LEGACY_PREFIX):])
    for k, v in (extra_headers or {}).items():
        request.headers[k] = v
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    path_qs = request.url.raw_path.decode("ascii")  # path + "?query" as sent on the wire
    request.headers["X-HRDD-Timestamp"] = ts
    request.headers["X-HRDD-Nonce"] = nonce
    request.headers["X-HRDD-Signature"] = sign(secret, ts, nonce, request.method, path_qs, request.content)


def _match_frontend(url: str) -> dict[str, Any] | None:
    from src.services.frontend_registry import registry
    best = None
    for fe in registry.list_all():
        base = fe.get("url", "").rstrip("/")
        if base and (url == base or url.startswith(base + "/")):
            if best is None or len(base) > len(best["url"].rstrip("/")):
                best = fe
    return best


class _RegistryAuth(httpx.Auth):
    """Signs requests for registered frontends that have a secret."""

    requires_request_body = True

    def auth_flow(self, request: httpx.Request):
        fe = _match_frontend(str(request.url))
        if fe and fe.get("signing_secret"):
            _sign_request(request, fe["signing_secret"], fe.get("extra_headers"))
        elif fe and fe["id"] not in _warned_unsigned:
            _warned_unsigned.add(fe["id"])
            logger.warning(
                f"Frontend {fe['id']} ({fe.get('name', '')}) has no signing secret — using the "
                f"legacy unsigned protocol. Configure a secret in Admin → Frontends."
            )
        yield request


class _ExplicitAuth(httpx.Auth):
    """Signs with explicit credentials (used to probe a URL before it is saved)."""

    requires_request_body = True

    def __init__(self, secret: str, extra_headers: dict[str, str] | None):
        self.secret = secret
        self.extra_headers = extra_headers

    def auth_flow(self, request: httpx.Request):
        _sign_request(request, self.secret, self.extra_headers)
        yield request


def AsyncClient(timeout: float | httpx.Timeout = 10.0, **kwargs: Any) -> httpx.AsyncClient:
    """Drop-in for httpx.AsyncClient for all backend → frontend traffic."""
    return httpx.AsyncClient(timeout=timeout, auth=_RegistryAuth(), **kwargs)


def ProbeClient(secret: str | None, extra_headers: dict[str, str] | None, timeout: float = 10.0) -> httpx.AsyncClient:
    """Client for a URL that is not (yet) in the registry, e.g. on register/edit."""
    if secret:
        return httpx.AsyncClient(timeout=timeout, auth=_ExplicitAuth(secret, extra_headers))
    return httpx.AsyncClient(timeout=timeout, headers=extra_headers or {})
