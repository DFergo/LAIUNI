#!/usr/bin/env python3
"""HRDD Helper — MCP server for installing and administering the app with an AI agent.

Local (stdio) MCP server, standard library only. It runs on the user's machine
before the app exists: it checks the machine, writes deployment folders, starts
the containers, then drives the backend's admin API (create the admin, connect
models, register frontends, run the tests).

Register it with the agent, e.g. Claude Code:
    claude mcp add hrdd -- python3 /path/to/HRDDHelper/ops/hrdd_mcp.py

Safety, enforced here and not only in the guides:
- Every change is planned first: tools that change something do nothing unless
  called with apply=true; destructive ones also need confirm_destructive=true;
  reading session contents or reports needs confirm_content=true.
- Secrets never go back to the chat: generated secrets are written to .env files
  (mode 0600) and masked in every answer. Request bodies can reference them as
  "env:/path/to/.env#KEY" and the value is read locally.

Human/CI use without an agent:  python3 hrdd_mcp.py call <tool> '<json arguments>'
"""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

SERVER_NAME = "hrdd-helper"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2025-06-18"

REPO = Path(__file__).resolve().parent.parent
GUIDES = Path(__file__).resolve().parent / "guides"
DEPLOY = REPO / "deploy"
STATE_DIR = Path(os.environ.get("HRDD_OPS_HOME", Path.home() / ".config" / "hrdd-ops"))

TOPOLOGIES = {
    "t3-same-host": "Backend and one frontend on this machine (trying it out, or a single server).",
    "backend": "Backend only (frontends on other machines: t1-lan, t2-vps-tailscale, t2-vps).",
    "t1-lan": "A frontend on another machine of the backend's LAN.",
    "t2-vps-tailscale": "A frontend on a VPS: users through a Cloudflare Tunnel, backend through Tailscale.",
    "t2-vps": "A frontend on a VPS without Tailscale: backend through a Cloudflare Access-protected hostname.",
}
SECRET_KEYS = re.compile(r"(secret|password|api_key|apikey|token|authorization|cf-access-client)", re.I)
CONTENT_PATHS = re.compile(r"^/admin/sessions/(?!lifecycle|resume-windows|purge)[^/?]+(/documents)?/?(\?.*)?$"
                           r"|^/admin/export/")
DESTRUCTIVE_PATHS = re.compile(r"(purge|reset|delete|import)", re.I)


# --------------------------------------------------------------------------- state

def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _state() -> dict[str, Any]:
    p = STATE_DIR / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(data: dict[str, Any]) -> None:
    _private_dir(STATE_DIR)
    _write_private(STATE_DIR / "state.json", json.dumps(data, indent=2))


def _mask(value: Any, key: str = "") -> Any:
    """Hide secrets in anything returned to the chat."""
    if isinstance(value, dict):
        return {k: _mask(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v, key) for v in value]
    if isinstance(value, str) and value and SECRET_KEYS.search(key):
        return "•••" + (f" (set, {len(value)} chars)" if not value.startswith("env:") else f" ({value})")
    return value


# --------------------------------------------------------------------------- env files

def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
            if m and not line.lstrip().startswith("#"):
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def _resolve_refs(value: Any) -> Any:
    """Replace "env:/path/.env#KEY" with the value, locally (never shown)."""
    if isinstance(value, dict):
        return {k: _resolve_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(v) for v in value]
    if isinstance(value, str) and value.startswith("env:") and "#" in value:
        path, key = value[4:].rsplit("#", 1)
        env = _read_env(Path(path).expanduser())
        if key not in env or not env[key]:
            raise ToolError(f"{key} is not set in {path}")
        return env[key]
    return value


def _fill_env(example: str, values: dict[str, str]) -> tuple[str, list[str]]:
    """Fill a .env.example: given values first, then generate empty secrets."""
    lines, generated = [], []
    for line in example.splitlines():
        m = re.match(r"([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if m:
            key, default = m.group(1), m.group(2)
            if key in values:
                line = f"{key}={values[key]}"
            elif not default and key.endswith("SECRET") and not key.endswith("PREVIOUS"):
                line = f"{key}={secrets.token_hex(32)}"
                generated.append(key)
        lines.append(line)
    return "\n".join(lines) + "\n", generated


# --------------------------------------------------------------------------- http

class ToolError(Exception):
    pass


def _http(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None,
          timeout: float = 30, raw: bytes | None = None) -> tuple[int, Any]:
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method.upper())
    if body is not None and raw is None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            text = r.read().decode(errors="replace")
            status = r.status
    except urllib.error.HTTPError as e:
        text, status = e.read().decode(errors="replace"), e.code
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise ToolError(f"Cannot reach {url}: {getattr(e, 'reason', e)}") from None
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def _backend(url: str | None = None) -> tuple[str, dict[str, str]]:
    st = _state()
    url = (url or st.get("backend_url") or "").rstrip("/")
    if not url:
        raise ToolError("No backend yet: call backend_connect with its address (e.g. http://127.0.0.1:8000).")
    token = st.get("tokens", {}).get(url)
    return url, ({"Authorization": f"Bearer {token}"} if token else {})


def _admin(method: str, path: str, body: Any = None, raw: bytes | None = None,
           headers: dict[str, str] | None = None) -> Any:
    url, auth = _backend()
    status, data = _http(method, url + path, body, {**auth, **(headers or {})}, timeout=120, raw=raw)
    if status == 401:
        raise ToolError("Not logged in or the session expired: call login.")
    if status >= 400:
        raise ToolError(f"{method} {path} → {status}: {data}")
    return data


# --------------------------------------------------------------------------- tool registry

TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None):
    def wrap(fn: Callable[..., Any]):
        TOOLS[name] = {"fn": fn, "schema": {
            "name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {}, "required": required or []}}}
        return fn
    return wrap


APPLY = {"type": "boolean", "description": "false (default) = only show what would change; true = do it. "
                                         "Ask the user before calling with true."}


def _plan(action: str, details: Any = None) -> dict[str, Any]:
    return {"planned": action, "details": _mask(details),
            "next": "Explain this to the user; if they agree, call again with apply=true."}


# ----- guides and profile

@tool("guide", "Read a setup/administration guide. Start with 'overview'. Topics: "
      + ", ".join(sorted(p.stem for p in GUIDES.glob("*.md"))) + ".",
      {"topic": {"type": "string"}}, ["topic"])
def guide(topic: str) -> str:
    path = GUIDES / f"{Path(topic).stem}.md"
    if not path.exists():
        raise ToolError(f"No guide '{topic}'. Available: {', '.join(sorted(p.stem for p in GUIDES.glob('*.md')))}")
    return path.read_text()


@tool("profile_save", "Save the onboarding survey answers (merged with earlier ones) so the setup can resume later. "
      "Never put secrets here.", {"answers": {"type": "object"}}, ["answers"])
def profile_save(answers: dict[str, Any]) -> dict[str, Any]:
    st = _state()
    st["profile"] = {**st.get("profile", {}), **answers, "updated": time.strftime("%Y-%m-%d %H:%M")}
    _save_state(st)
    return st["profile"]


@tool("profile_get", "Read the saved survey answers and the setup progress (backends and deployments known).")
def profile_get() -> dict[str, Any]:
    st = _state()
    return {"profile": st.get("profile", {}), "backend_url": st.get("backend_url"),
            "logged_in": sorted(st.get("tokens", {})), "deployments": st.get("deployments", {})}


# ----- machine

def _run(cmd: list[str], timeout: float = 20, cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, "not installed"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def _memory_gb() -> float | None:
    try:
        if sys.platform == "darwin":
            return int(_run(["sysctl", "-n", "hw.memsize"])[1]) / 1024 ** 3
        if Path("/proc/meminfo").exists():
            kb = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
            return kb / 1024 ** 2
    except (ValueError, AttributeError):
        pass
    return None


@tool("check_machine", "Read-only check of this machine: OS, CPU architecture, memory, GPU hints, free disk, and "
      "whether Docker, git, Tailscale, cloudflared, Ollama and LM Studio are installed, and which local models "
      "those servers offer.")
def check_machine() -> dict[str, Any]:
    arch = platform.machine().lower()
    mem = _memory_gb()
    gpu = "Apple Silicon (unified memory, Metal)" if sys.platform == "darwin" and arch in ("arm64", "aarch64") else None
    if gpu is None and shutil.which("nvidia-smi"):
        gpu = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])[1] or "NVIDIA"
    tools = {}
    for name, cmd in {"docker": ["docker", "--version"], "docker_compose": ["docker", "compose", "version"],
                      "git": ["git", "--version"], "tailscale": ["tailscale", "version"],
                      "cloudflared": ["cloudflared", "--version"], "ollama": ["ollama", "--version"],
                      "lm_studio": ["lms", "version"]}.items():
        code, out = _run(cmd)
        tools[name] = out.splitlines()[0] if code == 0 and out else None
    docker_running = _run(["docker", "info", "--format", "{{.ServerVersion}}"])[0] == 0 if tools["docker"] else False
    tailscale_ip = None
    if tools["tailscale"]:
        code, out = _run(["tailscale", "ip", "-4"])
        tailscale_ip = out.splitlines()[0] if code == 0 and out else None
    local_servers = {}
    for name, url, key in (("lm_studio", "http://127.0.0.1:1234/v1/models", "data"),
                           ("ollama", "http://127.0.0.1:11434/api/tags", "models")):
        try:
            status, data = _http("GET", url, timeout=3)
        except ToolError:
            continue
        if status == 200 and isinstance(data, dict):
            local_servers[name] = sorted(m.get("id") or m.get("name") for m in data.get(key) or [])
    disk = shutil.disk_usage(Path.home())
    return {
        "os": f"{platform.system()} {platform.release()}", "arch": arch,
        "memory_gb": round(mem, 1) if mem else None, "gpu": gpu, "cpus": os.cpu_count(),
        "free_disk_gb": round(disk.free / 1024 ** 3, 1), "tools": tools,
        "docker_running": docker_running, "tailscale_ip": tailscale_ip,
        "local_model_servers_running": local_servers,
        "backend_image": "published image fits" if arch in ("arm64", "aarch64", "x86_64", "amd64")
        else f"no published image for {arch}: build from source (deploy/backend/build-from-source.yml)",
        "local_models": ("enough memory for a 27–31B model (see guide 'models')" if mem and mem >= 32
                         else "chat models: use a cloud provider or another machine; embeddings can still run here"),
        "repo": str(REPO),
    }


# ----- deployments

@tool("deploy_prepare", "Create a deployment folder for a topology: copies its compose file and writes .env "
      "(mode 0600). Empty *SECRET values are generated; values can be given (use 'env:/path/.env#KEY' to copy a "
      "secret from another .env without showing it). Topologies: "
      + "; ".join(f"{k} — {v}" for k, v in TOPOLOGIES.items()),
      {"topology": {"type": "string", "enum": list(TOPOLOGIES)},
       "folder": {"type": "string", "description": "Where to create it, e.g. ~/hrdd/backend"},
       "values": {"type": "object", "description": "KEY: value for the .env (see the topology's .env.example)"},
       "apply": APPLY}, ["topology", "folder"])
def deploy_prepare(topology: str, folder: str, values: dict[str, str] | None = None, apply: bool = False):
    if topology not in TOPOLOGIES:
        raise ToolError(f"Unknown topology. Use one of: {', '.join(TOPOLOGIES)}")
    src = DEPLOY / topology
    dest = Path(folder).expanduser().resolve()
    example = (src / ".env.example").read_text()
    resolved = {k: str(_resolve_refs(v)) for k, v in (values or {}).items()}
    unknown = [k for k in resolved if not re.search(rf"^{k}=", example, re.M)]
    if unknown:
        raise ToolError(f"Not variables of {topology}: {', '.join(unknown)}. Its .env.example:\n{example}")
    env_text, generated = _fill_env(example, resolved)
    files = ["docker-compose.yml", ".env"]
    if (dest / ".env").exists():
        raise ToolError(f"{dest}/.env already exists: this folder already has a deployment. Choose another folder, "
                        "or edit that .env (env_set).")
    if not apply:
        return _plan(f"create {dest} with {', '.join(files)}",
                     {"env": _read_env_text(env_text), "secrets_generated": generated})
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "docker-compose.yml", dest / "docker-compose.yml")
    _write_private(dest / ".env", env_text)
    st = _state()
    st.setdefault("deployments", {})[str(dest)] = {"topology": topology, "created": time.strftime("%Y-%m-%d %H:%M")}
    _save_state(st)
    return {"created": str(dest), "files": files, "secrets_generated": generated,
            "env": _mask_env(dest / ".env")}


def _read_env_text(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return {k: _mask(v, k) for k, v in out.items()}


def _mask_env(path: Path) -> dict[str, Any]:
    return {k: _mask(v, k) for k, v in _read_env(path).items()}


@tool("env_show", "Show a deployment's .env with secrets masked.", {"folder": {"type": "string"}}, ["folder"])
def env_show(folder: str) -> dict[str, Any]:
    return _mask_env(Path(folder).expanduser() / ".env")


@tool("env_set", "Change values in a deployment's .env (mode 0600 kept). Values may be 'env:/path/.env#KEY'. "
      "Restart the deployment afterwards (compose action up).",
      {"folder": {"type": "string"}, "values": {"type": "object"}, "apply": APPLY}, ["folder", "values"])
def env_set(folder: str, values: dict[str, str], apply: bool = False) -> dict[str, Any]:
    path = Path(folder).expanduser() / ".env"
    if not path.exists():
        raise ToolError(f"No .env in {folder}")
    text = path.read_text()
    resolved = {k: str(_resolve_refs(v)) for k, v in values.items()}
    if not apply:
        return _plan(f"set {', '.join(resolved)} in {path}", {k: _mask(v, k) for k, v in resolved.items()})
    for key, val in resolved.items():
        if re.search(rf"^{key}=", text, re.M):
            text = re.sub(rf"^{key}=.*$", lambda _m: f"{key}={val}", text, flags=re.M)
        else:
            text += f"{key}={val}\n"
    _write_private(path, text)
    return {"updated": list(resolved), "env": _mask_env(path)}


@tool("secret_reveal", "Return one secret from a .env in clear text — it then passes through the chat and the model "
      "provider. Only when the user must copy it to another machine and the agent cannot do it itself; ask first.",
      {"folder": {"type": "string"}, "key": {"type": "string"}, "confirm_reveal": {"type": "boolean"}},
      ["folder", "key"])
def secret_reveal(folder: str, key: str, confirm_reveal: bool = False) -> str:
    if not confirm_reveal:
        raise ToolError("Ask the user first; then call with confirm_reveal=true. Prefer copying it with "
                        "'env:' references or scp, which keep it out of the chat.")
    value = _read_env(Path(folder).expanduser() / ".env").get(key)
    if not value:
        raise ToolError(f"{key} is not set")
    return value


@tool("compose", "Run docker compose in a deployment folder. Actions: ps, logs (read-only); up, pull, restart, "
      "down (change things: need apply=true). Never removes data volumes.",
      {"folder": {"type": "string"}, "action": {"type": "string", "enum": ["ps", "logs", "up", "pull", "restart", "down"]},
       "service": {"type": "string"}, "apply": APPLY}, ["folder", "action"])
def compose(folder: str, action: str, service: str = "", apply: bool = False) -> dict[str, Any]:
    dest = Path(folder).expanduser().resolve()
    if not (dest / "docker-compose.yml").exists():
        raise ToolError(f"No docker-compose.yml in {dest}")
    files = ["-f", "docker-compose.yml"] + (["-f", "build-from-source.yml"] if (dest / "build-from-source.yml").exists() else [])
    args = {"ps": ["ps"], "logs": ["logs", "--tail", "80"], "up": ["up", "-d"], "pull": ["pull"],
            "restart": ["restart"], "down": ["down"]}[action]
    if action == "up" and "build-from-source.yml" in files:
        args.append("--build")
    cmd = ["docker", "compose", *files, *args] + ([service] if service else [])
    if action not in ("ps", "logs") and not apply:
        return _plan(" ".join(cmd) + f"  (in {dest})")
    code, out = _run(cmd, timeout=1800 if action in ("up", "pull") else 120, cwd=dest)
    return {"command": " ".join(cmd), "exit_code": code, "output": out[-6000:]}


# ----- checks and tests

@tool("check_frontend", "Read-only checks of a frontend: public port (site and config answer; backend routes "
      "hidden) and, if given, the backend port (signed mode refuses unsigned requests). Never reads the queue.",
      {"public_url": {"type": "string"}, "backend_port_url": {"type": "string"}}, ["public_url"])
def check_frontend(public_url: str, backend_port_url: str = "") -> dict[str, Any]:
    pub = public_url.rstrip("/")
    checks = {}
    for path, want in (("/", 200), ("/internal/config", 200), ("/backend/v1/health", 404)):
        try:
            status, _ = _http("GET", pub + path, timeout=15)
        except ToolError as e:
            status = str(e)
        checks[f"public {path}"] = {"status": status, "expected": want, "ok": status == want}
    if backend_port_url:
        try:
            status, body = _http("GET", backend_port_url.rstrip("/") + "/backend/v1/health", timeout=15)
        except ToolError as e:
            status, body = str(e), None
        checks["backend port /backend/v1/health (unsigned)"] = {
            "status": status, "expected": "401 in signed mode (200 = trusted-network mode)", "ok": status in (401, 200)}
    return {"all_ok": all(c["ok"] for c in checks.values()), "checks": checks}


@tool("test_smoke", "End-to-end test through a frontend's public address, like a user: opens the response stream, "
      "sends a survey and one message, waits for the streamed reply. Creates one test session (token SMOKE-…) "
      "on the backend. Needs the frontend registered and a chat model configured.",
      {"public_url": {"type": "string"}, "message": {"type": "string"}, "language": {"type": "string"},
       "timeout_s": {"type": "number"}}, ["public_url"])
def test_smoke(public_url: str, message: str = "Hello, this is an installation test. Please answer in one sentence.",
               language: str = "en", timeout_s: float = 240) -> dict[str, Any]:
    pub = public_url.rstrip("/")
    token = f"SMOKE-{secrets.randbelow(9000) + 1000}"
    started = time.time()
    stream = urllib.request.urlopen(urllib.request.Request(f"{pub}/internal/stream/{token}"), timeout=timeout_s)
    status, _ = _http("POST", f"{pub}/internal/queue", {
        "session_token": token, "content": message, "message_id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "language": language,
        "survey": {"role": "worker", "type": "documentation", "language": language,
                   "company": "Installation test", "description": "Smoke test"}})
    if status != 200:
        raise ToolError(f"The frontend did not accept the message ({status}).")
    reply, event, lines, first = [], "", [], None
    try:
        for raw in stream:
            line = raw.decode(errors="replace").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                lines.append(line[6:] if line.startswith("data: ") else line[5:])
            elif not line:  # end of one SSE event
                data, lines = "\n".join(lines), []
                if event == "token":
                    first = first or time.time()
                    reply.append(data)
                elif event == "error":
                    return {"ok": False, "token": token, "error": data}
                elif event == "done":
                    break
            if time.time() - started > timeout_s:
                break
    except (socket.timeout, TimeoutError):
        pass
    finally:
        stream.close()
    text = "".join(reply).strip()
    return {"ok": bool(text), "token": token, "seconds_to_first_token": round(first - started, 1) if first else None,
            "seconds_total": round(time.time() - started, 1), "reply": text[:600] or None,
            "hint": None if text else "No reply: check the frontend is registered and online (admin_api GET "
                                      "/admin/frontends) and the chat model is healthy (GET /admin/llm/health)."}


@tool("test_unit", "Run the backend's unit tests in the backend image (read-only; takes a few minutes).")
def test_unit() -> dict[str, Any]:
    tests = sorted(p.stem for p in (REPO / "src/backend/tests").glob("test_*.py"))
    image = "ghcr.io/dfergo/laiuni-backend:latest"
    results = {}
    for name in tests:
        code, out = _run(["docker", "run", "--rm", "-v", f"{REPO / 'src/backend'}:/app/src", "-w", "/app", image,
                          "python", "-m", "unittest", f"src.tests.{name}"], timeout=600)
        results[name] = "OK" if code == 0 else out[-1500:]
    return {"all_ok": all(v == "OK" for v in results.values()), "results": results}


# ----- the app (admin API)

@tool("backend_connect", "Point the tools at a backend (its admin address, e.g. http://127.0.0.1:8000) and "
      "report whether its first admin account exists.", {"url": {"type": "string"}}, ["url"])
def backend_connect(url: str) -> dict[str, Any]:
    url = url.rstrip("/")
    status, data = _http("GET", url + "/admin/status", timeout=15)
    if status != 200 or not isinstance(data, dict):
        raise ToolError(f"{url} does not look like an HRDD backend ({status}).")
    st = _state()
    st["backend_url"] = url
    _save_state(st)
    return {"backend_url": url, "admin_exists": data.get("setup_complete"),
            "next": "login" if data.get("setup_complete") else "admin_create"}


def _password_file(url: str) -> Path:
    return STATE_DIR / f"admin-password-{re.sub(r'[^A-Za-z0-9]+', '_', url)}.txt"


@tool("admin_create", "Create the first admin account of a new backend with a strong generated password, saved "
      "only on this machine (mode 0600); returns the file path, never the password. Logs in.",
      {"apply": APPLY})
def admin_create(apply: bool = False) -> dict[str, Any]:
    url, _ = _backend()
    pw_file = _password_file(url)
    if not apply:
        return _plan(f"create the admin account of {url}; password saved in {pw_file}")
    password = secrets.token_urlsafe(18)
    status, data = _http("POST", url + "/admin/setup", {"password": password, "confirm_password": password})
    if status >= 400:
        raise ToolError(f"Setup refused ({status}): {data}")
    _private_dir(STATE_DIR)
    _write_private(pw_file, password + "\n")
    login()
    return {"admin_created": True, "password_file": str(pw_file),
            "tell_the_user": f"Your admin password is in {pw_file}. Store it in your password manager; "
                             "you need it to open the admin panel in the browser."}


@tool("login", "Log in to the current backend. With no password, uses the password file from admin_create or "
      "one the user saved (path given in the answer). Passing the password as an argument sends it through the chat.",
      {"password": {"type": "string"}})
def login(password: str = "") -> dict[str, Any]:
    url, _ = _backend()
    pw_file = _password_file(url)
    if not password:
        if not pw_file.exists():
            raise ToolError(f"No password file. Ask the user to save the admin password, alone, in {pw_file} "
                            "(e.g. open it in a text editor), then call login again.")
        password = pw_file.read_text().strip()
    status, data = _http("POST", url + "/admin/login", {"password": password, "remember_me": True})
    if status != 200 or not isinstance(data, dict) or "token" not in data:
        raise ToolError(f"Login failed ({status}).")
    st = _state()
    st.setdefault("tokens", {})[url] = data["token"]
    _save_state(st)
    return {"logged_in": url, "valid_for_hours": round(data.get("expires_in", 0) / 3600)}


@tool("admin_api", "Call the backend admin API (everything the admin panel does). GET reads freely, except "
      "session contents and exports (confirm_content=true, after asking the user each time). Other methods only "
      "show the plan unless apply=true; deleting, purging, resetting or importing also needs "
      "confirm_destructive=true. Body strings 'env:/path/.env#KEY' are replaced locally by that secret. "
      "Use admin_api_reference to find endpoints and fields; guide 'configure' explains each area.",
      {"method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]}, "path": {"type": "string"},
       "body": {"type": "object"}, "apply": APPLY, "confirm_destructive": {"type": "boolean"},
       "confirm_content": {"type": "boolean"}}, ["method", "path"])
def admin_api(method: str, path: str, body: dict[str, Any] | None = None, apply: bool = False,
              confirm_destructive: bool = False, confirm_content: bool = False) -> Any:
    method = method.upper()
    if not path.startswith("/admin/"):
        raise ToolError("Admin paths start with /admin/")
    bare = path.split("?")[0]
    if CONTENT_PATHS.search(bare) and method == "GET" and not confirm_content:
        raise ToolError("This returns conversation contents or reports. Ask the user, then call with "
                        "confirm_content=true (ask again next time).")
    if method != "GET":
        destructive = method == "DELETE" or bool(DESTRUCTIVE_PATHS.search(bare))
        if not apply:
            return _plan(f"{method} {path}" + (" — DESTRUCTIVE: also needs confirm_destructive=true" if destructive else ""), body)
        if destructive and not confirm_destructive:
            raise ToolError("Destructive change: confirm with the user, then call with confirm_destructive=true.")
    result = _admin(method, path, _resolve_refs(body) if body is not None else None)
    return _mask(result)


@tool("admin_api_reference", "List the backend's admin endpoints with their request fields (from the running "
      "backend, always current). Filter by text, e.g. 'frontends', 'llm', 'rag', 'smtp'.",
      {"filter": {"type": "string"}})
def admin_api_reference(filter: str = "") -> list[dict[str, Any]]:
    url, _ = _backend()
    status, spec = _http("GET", url + "/openapi.json")
    if status != 200 or not isinstance(spec, dict):
        raise ToolError("The backend did not return its API description.")
    schemas = spec.get("components", {}).get("schemas", {})
    out = []
    for path, ops in spec.get("paths", {}).items():
        if not path.startswith("/admin/") or (filter and filter.lower() not in path.lower()):
            continue
        for method, op in ops.items():
            entry: dict[str, Any] = {"method": method.upper(), "path": path, "summary": op.get("summary", "")}
            params = [p["name"] for p in op.get("parameters", []) if p.get("in") == "query"]
            if params:
                entry["query"] = params
            ref = (op.get("requestBody", {}).get("content", {}).get("application/json", {})
                   .get("schema", {}).get("$ref", ""))
            if ref:
                props = schemas.get(ref.rsplit("/", 1)[-1], {}).get("properties", {})
                entry["fields"] = {k: v.get("type") or [t.get("type") for t in v.get("anyOf", [])]
                                   for k, v in props.items()}
            if "multipart/form-data" in op.get("requestBody", {}).get("content", {}):
                entry["upload"] = "use admin_upload"
            out.append(entry)
    return out


@tool("admin_upload", "Upload a file to the admin API: knowledge-base documents (path /admin/rag/upload, "
      "optional query ?frontend_id=… for a campaign) or a frontend logo (/admin/frontends/{id}/branding/logo).",
      {"path": {"type": "string"}, "file": {"type": "string"}, "apply": APPLY}, ["path", "file"])
def admin_upload(path: str, file: str, apply: bool = False) -> Any:
    f = Path(file).expanduser()
    if not f.is_file():
        raise ToolError(f"No file {f}")
    if not path.startswith("/admin/"):
        raise ToolError("Admin paths start with /admin/")
    if not apply:
        return _plan(f"upload {f.name} ({f.stat().st_size // 1024} KB) to {path}")
    boundary = uuid.uuid4().hex
    raw = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{f.name}\"\r\n"
           f"Content-Type: application/octet-stream\r\n\r\n").encode() + f.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return _admin("POST", path, raw=raw, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


@tool("status", "Overview of the current backend: frontends (online, mode), model connections and slot health, "
      "embeddings, knowledge base, email. Read-only.")
def status() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, path in (("frontends", "/admin/frontends"), ("llm_health", "/admin/llm/health"),
                      ("embeddings", "/admin/llm/embedding-health"), ("knowledge_base", "/admin/rag/stats"),
                      ("smtp", "/admin/smtp")):
        try:
            out[key] = _mask(_admin("GET", path))
        except ToolError as e:
            out[key] = f"error: {e}"
    return out


# --------------------------------------------------------------------------- prompts

PROMPTS = {
    "start": ("Guided installation of HRDD Helper, from zero.",
              "Install HRDD Helper for me with the hrdd-helper MCP tools. First call guide('overview') and follow it: "
              "run the onboarding survey (guide 'onboarding') before recommending anything, save the answers with "
              "profile_save, and ask me before every step that changes something."),
    "add-frontend": ("Create, register and configure a new frontend.",
                     "Help me add a new frontend to HRDD Helper. Call guide('overview') and guide('frontends'), "
                     "check profile_get and status first, then guide me step by step."),
    "configure": ("Change the configuration of an installed backend.",
                  "Help me change the configuration of my HRDD Helper. Call guide('overview') and guide('configure'), "
                  "connect and log in, show me the current status, then ask what I want to change."),
    "diagnose": ("Find out why something does not work.",
                 "Something is not working in my HRDD Helper. Call guide('troubleshoot'), run the read-only checks "
                 "first (status, check_frontend, compose ps/logs), explain what you find, then propose fixes."),
    "update": ("Update the app and back it up.",
               "Help me update HRDD Helper and back it up. Call guide('operate') and follow it."),
}


# --------------------------------------------------------------------------- JSON-RPC

def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Unknown tool {name}"}], "isError": True}
    try:
        result = TOOLS[name]["fn"](**(args or {}))
        text = result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except ToolError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except TypeError as e:
        return {"content": [{"type": "text", "text": f"Bad arguments: {e}"}], "isError": True}
    except Exception as e:  # report, keep the server alive
        return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if mid is None:  # notification
        return None
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                  "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                  "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                  "instructions": "Installs and administers HRDD Helper. Start with the 'start' prompt or "
                                  "guide('overview'). Ask the user before any call with apply=true."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [t["schema"] for t in TOOLS.values()]}
    elif method == "tools/call":
        result = _call_tool(params.get("name", ""), params.get("arguments") or {})
    elif method == "prompts/list":
        result = {"prompts": [{"name": k, "description": d} for k, (d, _) in PROMPTS.items()]}
    elif method == "prompts/get":
        name = params.get("name", "")
        if name not in PROMPTS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown prompt {name}"}}
        desc, text = PROMPTS[name]
        result = {"description": desc, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
    elif method == "resources/list":
        result = {"resources": [{"uri": f"hrdd://guides/{p.stem}", "name": p.stem, "mimeType": "text/markdown"}
                                for p in sorted(GUIDES.glob("*.md"))]}
    elif method == "resources/read":
        uri = params.get("uri", "")
        try:
            text = guide(uri.rsplit("/", 1)[-1])
        except ToolError as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": str(e)}}
        result = {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "call":
        out = _call_tool(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
        print(out["content"][0]["text"])
        sys.exit(1 if out["isError"] else 0)
    serve()
