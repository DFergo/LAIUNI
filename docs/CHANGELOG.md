# HRDD Helper — Changelog

## v2.0 — Clean Rewrite

### Sprint 2 — Backend Core: Admin Auth + Config (2026-03-09)
- `src/backend/core/config.py`: Pydantic config loader for `deployment_backend.json`
- `src/backend/api/v1/admin/auth.py`: Admin setup, login, JWT auth (HS256, bcrypt)
- Admin React app (`src/admin/`): SetupPage, LoginPage, Dashboard with UNI colors
- First-run flow: "Create Admin Account" → bcrypt hash → `/app/data/.admin_hash`
- JWT: 24h default expiry, 30d with "remember me", verify endpoint
- Backend Dockerfile: multi-stage (Node build for admin SPA + Python runtime)
- Backend serves admin SPA at `/` root via FastAPI catch-all route

### Sprint 1 — Project Scaffolding (2026-03-09)
- `Dockerfile.backend`: Python 3.11-slim + FastAPI + uvicorn
- `Dockerfile.frontend`: Multi-stage (Node 20 build → Python 3.11-slim runtime with Nginx + supervisord)
- 3 Docker Compose files: backend (8000), frontworker (8091), frontorganizer (8090)
- Backend: FastAPI skeleton with `/health` endpoint
- Frontend: React 18 + Vite 6 + Tailwind 3.4 with UNI color palette
- Frontend sidecar: FastAPI skeleton with `/internal/health`
- Nginx config: SSE streaming headers, SPA fallback, sidecar proxy
- supervisord manages Nginx + sidecar in frontend container
- All containers verified: build, run, health checks, /app/data volumes

### Sprint 0 — Project Setup (2026-03-09)
- Created product specification (SPEC-v2.md)
- Set up project structure for Claude Code
- Created GitHub repo: https://github.com/DFergo/LAIUNI

---

## v1.x — Previous Version (archived)

### Sprint 11f-fix
- Removed PreChatPage component
- Fixed nginx SSE buffering
- Added debug logging
- Fixed placeholder IP

### Sprint 11f
- Removed frontend_id shared secret
- Simplified frontend registration (auto-generated IDs)
- Introduced chat regression (not resolved)

### Sprint 11e
- Removed frontend admin panel
- Split compose per frontend type
- Standardized ports (8090 organizer, 8091 worker)

### Sprint 11d
- Admin cleanup
- Hostname-based frontend auto-discovery

### Sprint 11b+11c
- Admin UI improvements
- Session finalization (summary + report)
- Docker split (separate Dockerfiles for backend and frontend)

### Sprint 11b
- Multi-step user flow (language → disclaimer → session → auth → survey → chat)
- Markdown chat rendering

### Sprint 11a ✓ (Last working version)
- Prompt loading architecture
- Survey integration
- Chat flow working end-to-end

### Sprint 10a
- LLM provider abstraction (LM Studio + Ollama)
- Production deployment configs

### Sprint 9
- Security layer (injection detection, guardrails, rate limiting)

### Sprint 8
- Admin Panel (prompts, RAG, frontends, sessions, LLM, SMTP tabs)
