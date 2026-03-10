# HRDD Helper — Project Status

**Last Updated:** 2026-03-09

## Current State: v2 Rewrite — Sprint 7a Complete, Sprint 7b Next

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

### Sprint 5 — LLM Integration ✅

**Goal:** Real AI responses via LM Studio or Ollama.

#### Deliverables
- [x] `services/llm_provider.py` — LM Studio + Ollama abstraction (OpenAI-compatible API)
- [x] `services/prompt_assembler.py` — system + role + mode + context(survey) assembly
- [x] `services/session_history.py` — in-memory conversation history per session
- [x] `api/v1/admin/llm.py` — health, models, settings endpoints
- [x] 11 default prompt files (core, 4 roles, 3 modes, context template, 2 post-processing)
- [x] Admin LLM tab (provider health, model select, parameters)
- [x] `<think>` block filtering for Qwen3 reasoning tokens
- [x] Mock LLM fallback when no provider available
- [x] LLM settings persisted to `/app/data/llm_settings.json`

#### Acceptance Criteria
- [x] Backend connects to LM Studio — verified with qwen/qwen3-235b-a22b
- [x] Backend connects to Ollama — verified online
- [x] Admin LLM tab shows online/offline status for each provider
- [x] Admin can select model, set temperature, num_ctx, max_tokens
- [x] User message → real LLM response streams back to chat
- [x] Prompt includes: system prompt + role prompt + mode prompt + survey context
- [x] Conversation history maintained per session
- [x] LLM failure → graceful error message to user (not crash)
- [x] check_health() wrapped in try-except
- [x] _safe_process wrapped in try-except, pushes error to stream
- [x] Mock LLM fallback works when no provider available

### Sprint 5b — LLM Tab Improvements ✅

- [x] Split LLM tab into Inference and Context Compression (Letta) subpanels
- [x] Toggle to enable/disable Letta summariser
- [x] Context window (num_ctx) for Ollama on both panels
- [x] Hints with recommended values and page equivalents
- [x] Fix: health refresh no longer overwrites unsaved edits
- [x] Discard Changes and Reset to Defaults buttons

### Sprint 6 — Admin Panel Complete ✅

**Goal:** All 6 admin tabs functional.

#### Deliverables
- [x] **Prompts tab**: two-column editor, 5 categories, save with dirty tracking
- [x] **RAG tab**: upload docs (.md/.txt/.json), list, delete, reindex stub
- [x] **Sessions tab**: list with All/Flagged filters, view conversation detail, flag/unflag
- [x] **SMTP tab**: config form (host, port, user, pass, from, admin notify, TLS), test stub
- [x] Backend endpoints: prompts CRUD, RAG file management, sessions list/detail/flag, SMTP config
- [x] Fix: survey `type` always sent (was missing for worker/representative → caused "unknown" mode)
- [x] Default mode fallback: "documentation" instead of "unknown"

#### Backend Endpoints
- `GET/PUT /admin/prompts`, `GET/PUT /admin/prompts/{name}` — prompts CRUD
- `GET/PUT /admin/sessions`, `GET /admin/sessions/{token}`, `PUT /admin/sessions/{token}/flag`
- `POST /admin/rag/upload`, `GET /admin/rag/documents`, `DELETE /admin/rag/documents/{name}`, `POST /admin/rag/reindex`
- `GET/PUT /admin/smtp`, `POST /admin/smtp/test`

### Sprint 6b — Knowledge Base ✅

- [x] `glossary.json` — 15 domain terms with translations in 6 languages
- [x] `organizations.json` — 14 unions, federations, and institutions
- [x] Backend endpoints: `/admin/knowledge/glossary`, `/admin/knowledge/organizations` (GET/PUT)
- [x] Prompt assembler: glossary + organizations injected as layer 5 in every session
- [x] Admin panel: Glossary and Organizations Directory sections in RAG tab with inline editors
- [x] Default files installed on first startup
- [x] Spec updated: §4.2.4, §11, §13.1-13.4 (guardrails, session integrity, internal assessment, phase-based prompts)
- [x] Milestones updated: Sprint 8 includes internal assessment, Sprint 10 = guardrails
- [x] `docs/knowledge/prompt-assembly-flow.md` — full prompt architecture documentation
- [x] `docs/INSTALL.md` — installation and usage guide

### Sprint 7a — RAG (LlamaIndex) ✅

- [x] `services/rag_service.py` — LlamaIndex indexing + retrieval with sentence-transformers
- [x] Embedding model: `all-MiniLM-L6-v2` (downloaded from HuggingFace on first run)
- [x] Index built from `/app/data/documents/` and persisted to `/app/data/rag_index/`
- [x] Reindex endpoint connected to real indexing (was stub)
- [x] RAG chunks injected per-message in polling (not in system prompt)
- [x] Index loads from disk on restart (no re-embedding needed)
- [x] Dependencies: `llama-index-core`, `llama-index-readers-file`, `llama-index-embeddings-huggingface`, `sentence-transformers`

### What's Needed Next
- **Sprint 7b:** Context compression (Letta or simpler approach)
- **Sprint 8:** Session management + finalization
- **Sprint 9:** SMTP integration
- **Sprint 10:** Ethical guardrails
- **Sprint 11:** Polish + production deployment

---

## Previous Version (v1) History

v1 was developed from Sprint 8 through Sprint 11f. The chat flow worked in Sprint 11a but regressed in later sprints. A bisection effort was underway but the codebase had accumulated enough technical debt to warrant a clean rewrite.

Key lessons from v1 are documented in `docs/knowledge/lessons-learned.md`.
