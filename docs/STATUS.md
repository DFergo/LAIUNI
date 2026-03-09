# HRDD Helper — Project Status

**Last Updated:** 2026-03-09

## Current State: v2 Rewrite — Sprint 4 Complete, Sprint 5 Next

### Sprint 0 — Project Setup ✅
- [x] Product specification written (SPEC-v2.md)
- [x] Project structure created
- [x] Claude Code configuration ready
- [x] GitHub repo created (https://github.com/DFergo/LAIUNI)
- [x] Deployment configs created
- [x] Nginx config created

### Sprint 1 — Project Scaffolding ✅

**Goal:** Both containers build and run (empty shells)

#### Deliverables
- [x] `Dockerfile.backend` — Python 3.11 + FastAPI
- [x] `Dockerfile.frontend` — Node 20 build + Nginx + Python sidecar (supervisord)
- [x] `docker-compose.backend.yml` — port 8000, hrdd-data volume
- [x] `docker-compose.frontworker.yml` — port 8091, hrdd-fw-data volume
- [x] `docker-compose.frontorganizer.yml` — port 8090, hrdd-fo-data volume
- [x] `src/backend/main.py` — FastAPI app with health endpoint
- [x] `src/backend/requirements.txt` — dependencies
- [x] `src/frontend/package.json` — React 18 + Vite 6 + Tailwind 3.4
- [x] `src/frontend/tailwind.config.js` — UNI colors configured
- [x] `src/frontend/vite.config.ts`
- [x] `src/frontend/src/App.tsx` — "Hello HRDD" placeholder
- [x] Frontend sidecar (`src/frontend/sidecar/main.py`) — minimal FastAPI
- [x] `config/supervisord.conf` — runs Nginx + sidecar in frontend container

#### Acceptance Criteria
- [x] `docker compose -f docker-compose.backend.yml build` succeeds
- [x] `docker compose -f docker-compose.frontworker.yml build` succeeds
- [x] Backend responds to `GET http://localhost:8000/health` → `{"status": "ok"}`
- [x] Frontend loads React app at `http://localhost:8091`
- [x] Frontend Nginx proxies `/internal/` to sidecar (returns 404, not 502)
- [x] Data directories exist inside containers at `/app/data`

### Sprint 2 — Backend Core: Admin Auth + Config ✅

**Goal:** Backend admin login works. Config loader ready.

#### Deliverables
- [x] `src/backend/core/config.py` — Pydantic config loader (BackendConfig)
- [x] `src/backend/api/v1/admin/auth.py` — Setup, login, JWT (HS256, no external deps)
- [x] Admin React app (`src/admin/`) — SetupPage, LoginPage, Dashboard
- [x] First-run flow: create password → bcrypt hash to `/app/data/.admin_hash`
- [x] JWT auth: 24h default, 30 days with "remember me"
- [x] Backend serves admin SPA at `/` (root) via FastAPI catch-all

#### Acceptance Criteria
- [x] First visit to `http://localhost:8000` shows "Create Admin Account"
- [x] After creating password, shows login form
- [x] Login returns JWT, redirects to admin dashboard
- [x] Invalid password shows error message
- [x] JWT persists across page reloads (stored in localStorage)
- [x] "Remember me" extends JWT expiry (24h → 30d)
- [x] `deployment_backend.json` loaded and validated by Pydantic
- [x] Deleting `.admin_hash` resets to first-run setup

### Sprint 3 — Frontend User Flow ✅

**Goal:** Complete user journey from language selection to survey submission.

#### Deliverables
- [x] `LanguageSelector.tsx` — 16 languages in responsive 4-column grid
- [x] `DisclaimerPage.tsx` — translated purpose statement + accept button
- [x] `SessionPage.tsx` — new session (WORD-NUMBER token) + recover
- [x] `AuthPage.tsx` — email verification (organizer only, mock until Sprint 9)
- [x] `SurveyPage.tsx` — role-dependent fields per §3.4 matrix
- [x] `ChatShell.tsx` — placeholder with session token
- [x] `App.tsx` — phase state machine (loading → language → ... → chat)
- [x] `i18n.ts` — 16 languages with all UI strings
- [x] `types.ts` — TypeScript types for Phase, Role, DeploymentConfig, SurveyData
- [x] `token.ts` — WORD-NUMBER generator (24 nature words + 4-digit random)
- [x] Frontend sidecar: `GET /internal/config` reads deployment JSON

#### Acceptance Criteria
- [x] Language selector shows 16 languages in responsive grid
- [x] Clicking a language → disclaimer page in that language
- [x] Accept disclaimer → session page
- [x] "New session" generates `WORD-NUMBER` token and displays it
- [x] Worker: session → survey (skip auth)
- [x] Organizer: session → auth → survey
- [x] Survey shows correct fields per role (§3.4 matrix)
- [x] Survey submit → chat placeholder
- [x] Session recovery: entering valid token loads previous state (mock, full in Sprint 8)
- [x] Colors match: header #003087, cards white/rounded-xl, buttons uni-blue
- [x] Footer shows disclaimer text, hidden during chat phase
- [x] Sidecar returns correct config per deployment JSON

### Sprint 4 — Message Queue + Polling ✅

**Goal:** Pull-inverse pipeline works end-to-end with mock responses.

#### Deliverables
- [x] Frontend sidecar: `POST /internal/queue`, `GET /internal/queue`, `POST /internal/stream/{token}/chunk`, `GET /internal/stream/{token}` (SSE)
- [x] Backend: `services/polling.py` — background polling loop with sequential processing
- [x] Backend: `services/frontend_registry.py` — persistent JSON registry (atomic writes)
- [x] Backend: admin frontends tab (register via /internal/config discovery, enable/disable, remove)
- [x] `ChatShell.tsx` — real chat with EventSource SSE streaming
- [x] Queue position feedback to user
- [x] 31 languages supported (15 new with English fallback)

#### Acceptance Criteria
- [x] User sends message → sidecar queue → backend polls → mock response streams back
- [x] SSE events: token, done, error, queue_position
- [x] EventSource onerror unblocks UI after 3 failures
- [x] Message TTL: 300s
- [x] Frontend registry persists to JSON (atomic write)
- [x] Admin can register/enable/disable frontends
- [x] Chat bubbles: user right/blue, assistant left/white
- [x] Queue position shown while waiting

### What's Needed Next
- **Sprint 5:** LLM integration
- **Sprint 6:** Admin panel (all 6 tabs)
- **Sprint 7:** RAG + MemGPT/Letta
- **Sprint 8:** Session management + finalization
- **Sprint 9:** SMTP integration
- **Sprint 10:** Polish + production deployment

---

## Previous Version (v1) History

v1 was developed from Sprint 8 through Sprint 11f. The chat flow worked in Sprint 11a but regressed in later sprints. A bisection effort was underway but the codebase had accumulated enough technical debt to warrant a clean rewrite.

Key lessons from v1 are documented in `docs/knowledge/lessons-learned.md`.
