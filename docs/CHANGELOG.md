# HRDD Helper — Changelog

## v2.0 — Clean Rewrite

### Sprint 4 — Message Queue + Polling (2026-03-09)
- Full pull-inverse pipeline: React → sidecar queue → backend poll → mock LLM → SSE stream → React
- Frontend sidecar: `POST /internal/queue`, `GET /internal/queue`, `POST /internal/stream/{token}/chunk`, `GET /internal/stream/{token}` (SSE)
- Backend polling loop with sequential processing (one message at a time for LLM constraint)
- Queue position feedback via SSE (`queue_position` event)
- Frontend registry: persistent JSON with atomic writes (lesson #5), auto-discovery via `/internal/config`
- Admin Frontends tab: register by URL, enable/disable, remove, status indicators (green/red/gray), auto-refresh
- `ChatShell.tsx`: real chat with EventSource streaming, user bubbles right/blue, assistant left/white
- EventSource error handling: UI unblocks after 3 consecutive failures (lesson #1)
- Message TTL: 300s expiry in sidecar queue
- 31 languages supported (15 new with English fallback via `Partial<Record>` pattern)
- Survey fields: all visible on both frontends, required varies by frontend type

### Sprint 3 — Frontend User Flow (2026-03-09)
- Complete phase state machine: loading → language → disclaimer → session → auth? → survey → chat
- 16 languages with full UI translations (EN, ES, FR, DE, PT, AR, ZH, HI, ID, JA, KO, RU, TR, VI, TH, SW)
- LanguageSelector: responsive 4-column grid with native language names
- DisclaimerPage: translated purpose statement per language
- SessionPage: WORD-NUMBER token generation (24 nature words + 4-digit random)
- AuthPage: email verification flow (mock, SMTP in Sprint 9)
- SurveyPage: role-dependent fields matching §3.4 matrix exactly
- ChatShell: placeholder with session token display
- Frontend sidecar: `/internal/config` endpoint reads deployment JSON
- Organizer frontend shows auth step, worker skips it
- Footer with disclaimer, hidden during chat phase

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
