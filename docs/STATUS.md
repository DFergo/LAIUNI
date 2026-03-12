# HRDD Helper — Project Status

**Last Updated:** 2026-03-12

## Current State: v2 Rewrite — Sprint 11 DONE

### Sprint 11 — Polish, Copyright, Branding, Notifications

**Goal:** Pre-production polish — legal compliance, UX navigation, per-frontend branding, notification routing.

#### Block 1 — Copyright + Licensing (S) ✅
- [x] `LICENSE` file at repo root (proprietary, UNI Global Union)
- [x] Copyright headers in key files (backend main.py, frontend App.tsx, sidecar main.py)
- [x] Visible footer "© UNI Global Union" in frontend
- [x] Update package.json with author + license

#### Block 2 — Navigation UX: Back buttons + reload warning (M) ✅
- [x] Back button on all pre-chat pages (Disclaimer, Session, RoleSelect, Auth, Instructions, Survey)
- [x] Warning in Instructions page about not reloading
- [x] `beforeunload` handler during active session (chat + survey phases)
- [x] `history.pushState` so browser back goes to previous step (not out of app)

#### Block 3 — Multiple notification recipients (M) ✅
- [x] SMTP config: `notification_emails` as list (not single address), backward compat migration
- [x] Admin SMTP tab: multi-email chip/tag input for global notification recipients
- [x] Per-frontend notification emails in campaign config (`/app/data/campaigns/{fid}/notification_config.json`)
- [x] Admin SMTP tab: per-frontend notification recipients section
- [x] `smtp_service.py`: `_resolve_notification_recipients()` merges frontend-specific + global, deduplicates
- [x] `notify_admin_report` accepts `frontend_id`, sends to all resolved recipients
- [x] Backend API: `GET/PUT /admin/smtp/frontend-notifications/{frontend_id}`

#### Block 4 — Per-frontend branding (M) ✅
- [x] Admin config per frontend: app title, disclaimer text, instructions text, logo URL
- [x] Admin Frontends tab: "Branding" button per frontend with expandable editor
- [x] Backend API: `GET/PUT /admin/frontends/{id}/branding`
- [x] Backend pushes branding to sidecar via `POST /internal/branding` (on save + during polling)
- [x] Sidecar stores branding in memory, serves via `/internal/config` response
- [x] React pages use per-frontend branding when available, UNI defaults when not
- [x] Header title, disclaimer text, instructions text, and logo on all pages (language, disclaimer, instructions) use branding
- [x] Persisted to `/app/data/campaigns/{frontend_id}/branding.json`

#### Acceptance Criteria
- [ ] LICENSE file present, copyright in key source files
- [ ] Back button works on every pre-chat page
- [ ] Browser reload during session shows confirmation dialog
- [ ] Browser back navigates to previous step
- [ ] Admin can configure title, disclaimer, instructions per frontend
- [ ] Frontend displays per-frontend branding or UNI defaults
- [ ] Admin can configure multiple notification emails (global + per frontend)
- [ ] Notifications sent to all configured recipients

---

### Upcoming Sprints

| Sprint | Content |
|--------|---------|
| **12** | Redactar presentación/disclaimer/instrucciones + traducción completa 31 idiomas |
| **13** | Migración frontends Mac Mini + Monitorización Telegram |
| **14** | Test de calidad intensivo (E2E, prompts can/cannot, respuestas simples, security) |
| **15** | Letta/MemGPT |
| **Final** | Limpieza archivos Claude Code del repo público GitHub |

---

## Completed Sprints

### Sprint 10 — Guardrails + Repetition Detection + Polish ✅

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

### Sprint 7b — Context Compression ✅

**Goal:** Prevent context overflow in long conversations via token counting + LLM-based compression.

**Decision:** Simple compression with existing LLM instead of Letta (see ADR-009). Letta deferred to Sprint 12.

#### Deliverables
- [x] `services/context_compressor.py` — token counter + incremental compression with running summary
- [x] `prompts/context_compression.md` — dedicated compression prompt (preserves names, dates, facts, case data)
- [x] Token estimation before each LLM call (logged per message)
- [x] Compression at configurable threshold (slider 50-90%, default 75%)
- [x] Progressive: oldest messages compressed first, recent 4 kept intact
- [x] Integration in `polling.py` — compress after RAG injection, before inference
- [x] Uses summariser model/provider from admin LLM settings
- [x] Logging with before/after token counts
- [x] Admin LLM tab: context window for all providers, threshold slider, model auto-correction
- [x] ADR-009 documented, Sprint 12 (Letta) planned
- [x] `/git` command for dual-remote push (GitHub + Gitea)

### Sprint 7c — User Flow Redesign + Monolithic Prompts ✅

**Goal:** Reorganize the user flow sequence and replace modular prompt concatenation with monolithic per-profile+case prompts for higher precision.

**Idea source:** `docs/ideas.md` — "Prompts monolíticos por perfil+caso"

#### Part 1: New User Flow Sequence

Current: language → disclaimer → session → auth → survey → chat
New: language → disclaimer → session (new/recover) → **role selection** → auth (if required) → **instructions page** → survey → chat

- [x] `types.ts` — Add new phases: `role_select`, `instructions`. Add new consultation modes: `interview`, `submit`
- [x] `App.tsx` — Reorder phase state machine to new sequence. Pass selected role to subsequent phases
- [x] `RoleSelectPage.tsx` (NEW) — Profile selection page
  - frontworker: Worker, Representative (2 cards)
  - frontorganizer: Organizer, Officer (2 cards) — Interview mode eliminates need for worker/rep here
  - Clean card-based UI matching existing design (UNI blue, rounded-xl, shadow-md)
- [x] `InstructionsPage.tsx` (NEW) — Hardcoded instructions per profile
  - Brief explanation of what this profile does and what to expect
  - Translated via i18n (all 31 languages)
  - "Continue" button to proceed to survey
- [x] `i18n.ts` — Add strings for role selection page + instructions page (all profiles, all languages)

#### Part 2: Survey Adaptation

- [x] `SurveyPage.tsx` — Role comes from previous phase (no longer selected in survey)
  - Mode selector shown only for Organizer/Officer, options depend on profile:
    - Organizer: Document, Interview, Advisory, Submit (pending confirmation), Training (pending confirmation)
    - Officer: Document, Interview, Advisory, Submit (pending confirmation), Training
  - Field requirements:
    - Worker/Rep: company, country/region, description required. Identity optional (note: anonymous allowed, contact recommended)
    - Organizer/Officer: all required, except company optional in advisory/training
  - Privacy note for worker/rep: "Anonymous interactions are allowed to protect your privacy, but providing contact details is strongly recommended so we can follow up"

#### Part 3: Prompt Restructure

- [x] `prompt_assembler.py` — Replace modular assembly (core+role+mode) with:
  1. System prompt (`core.md`) — universal instructions
  2. Case prompt (`{profile}_{case}.md` or `{profile}.md`) — monolithic per combination
  3. Context template (`context_template.md`) — survey data substitution
  4. Knowledge base (glossary for non-EN + organizations)
  - Prompt files needed:
    - `worker.md` — single prompt for worker
    - `worker_representative.md` — single prompt for representative
    - `organizer_document.md`
    - `organizer_interview.md`
    - `organizer_advisory.md`
    - `organizer_submit.md` (pending confirmation)
    - `officer_document.md`
    - `officer_interview.md`
    - `officer_advisory.md`
    - `officer_submit.md` (pending confirmation)
    - `officer_training.md`
  - Remove old role-only prompts: `organizer.md`, `officer.md`
  - Remove old mode-only prompts: `documentation.md`, `advisory.md`, `training.md`
- [x] Admin Prompts tab — Update categories to reflect new prompt structure

#### Part 4: Backend Adjustments

- [x] `polling.py` — No structural changes expected (prompt assembler handles the rest)
- [x] `session_history.py` — Store selected role separately from survey (role now comes from earlier phase)
- [x] Sidecar `/internal/queue` — Ensure role is passed in the message payload

#### Acceptance Criteria
- [x] New flow works on frontworker: language → disclaimer → session → role (worker/rep) → instructions → survey → chat
- [x] New flow works on frontorganizer: language → disclaimer → session → role (organizer/officer) → auth → instructions → survey → chat
- [x] Role selection page shows correct options per frontend type
- [x] Instructions page shows profile-specific text in selected language
- [x] Survey fields adapt correctly to role selected in previous phase
- [x] Mode selector appears only for organizer/officer with correct options
- [x] Worker/Rep: anonymous allowed, only company+country+description required
- [x] Organizer/Officer: all fields required, company optional in advisory/training
- [x] Monolithic case prompts load correctly for each profile+case combination
- [x] System prompt structure: core + case prompt + context template + knowledge
- [x] Chat responses are coherent and profile-appropriate
- [x] Existing chat, polling, compression, RAG unaffected
- [x] Mobile: full flow works on phone browsers without breaking

#### Notes
- Daniel will provide final prompt content for each case file
- "Submit" mode pending confirmation — implement the slot, content TBD
- SPEC-v2.md needs updating before starting (new modes, reordered flow)
- Prompt files can start as placeholders with clear structure, Daniel fills content later

### Sprint 8a — Session Persistence to Disk ✅

**Goal:** Sessions survive backend restarts. All session data written to `/app/data/sessions/{token}/` in real time.

**Current state:** Everything in-memory (`session_history.py` singleton dict). Lost on restart. `config.py` defines `sessions_path` but it's unused.

#### Deliverables
- [x] `services/session_store.py` — New service: disk-backed session persistence
  - `init_session(token, system_prompt, survey, language)` → creates `{token}/session.json`
  - `append_message(token, role, content)` → appends to `{token}/conversation.jsonl`
  - `get_session(token)` → reads from disk
  - `list_sessions()` → scans session directories
  - Atomic writes for `session.json` (tmp + rename)
- [x] `session.json` per session: metadata (survey, language, role, mode, timestamps, status, flagged)
- [x] `conversation.jsonl` per session: one JSON line per message `{role, content, timestamp}`
- [x] Integrate into `polling.py`: write to disk after each message (user + assistant)
- [x] Integrate into admin `sessions.py`: read from disk instead of in-memory
- [x] Session status field: `active` | `completed` | `flagged`
- [x] Flag toggle persists to disk (currently in-memory only)
- [x] Load existing sessions on startup (scan `/app/data/sessions/`)
- [x] Keep in-memory cache for active sessions (performance), disk as source of truth

#### Acceptance Criteria
- [x] `session.json` created on first message with correct metadata
- [x] `conversation.jsonl` grows with each message exchange
- [x] Backend restart → sessions still visible in admin panel
- [x] Flag toggle persists across restart
- [x] Admin session list shows all sessions (active + old)
- [x] Admin session detail shows full conversation from disk
- [x] No performance regression in chat flow (in-memory cache for active)

---

### Sprint 8b — Session Recovery ✅

**Goal:** Users can resume sessions by entering their token. Recovery skips role select, instructions, and survey.

**Depends on:** Sprint 8a (disk persistence)

#### Deliverables
- [x] Recovery via pull-inverse: frontend → sidecar queue → backend resolves → pushes data back
- [x] Sidecar: `POST /internal/session/recover` (request), `GET /internal/session/{token}/recover` (poll result), `POST /internal/session/{token}/recovery-data` (backend pushes)
- [x] Backend: `_handle_recovery()` in polling.py — reads session from disk, pushes to sidecar
- [x] Hybrid recovery: compression summary for long sessions, full messages for short ones
- [x] Compression summaries persisted to `{token}/compression_summary.json`
- [x] Frontend `App.tsx`: recover → poll sidecar → restore language, role, survey → skip to chat
- [x] Frontend `SessionPage.tsx`: loading state ("Recovering..."), error display
- [x] Frontend `ChatShell.tsx`: recovery context shown (summary or previous messages + "Session resumed" separator)
- [x] Resume window enforcement: 120h max (backend-side safety check)
- [x] Expired/invalid token → clear error message

#### Acceptance Criteria
- [x] Enter valid token → chat resumes with previous conversation visible
- [x] Language, role, survey data restored (no re-entry)
- [x] Recovery skips: role select, instructions, survey (go straight to chat)
- [x] Invalid token → error message
- [x] Pull-inverse architecture respected (frontend doesn't call backend directly)
- [x] Conversation coherence maintained after recovery

---

### Sprint 8c — End Session + Summary (DONE)

**Goal:** User can end session. Summary is generated and streamed to chat as final message.

**Depends on:** Sprint 8a (disk persistence)

#### Deliverables
- [x] "End Session" button in ChatShell (red border, per spec §3.5)
- [x] Frontend sends `finalize: true` in message payload (spec §8.1)
- [x] Backend detects `finalize` flag in polling
- [x] Summary generation: per-profile prompts (`session_summary_{role}.md`) + full conversation → LLM inference
- [x] Summary streamed to chat as final assistant message (user sees it)
- [x] Summary saved as `/app/data/sessions/{token}/summary.md` and as conversation message
- [x] Session status set to `completed`
- [x] Chat input disabled after finalization
- [x] Confirmation dialog before ending ("Are you sure?")
- [x] Recovered completed sessions are read-only
- [x] Markdown rendering (react-markdown + remark-gfm) in chat, streaming, recovery, and admin
- [x] Smart auto-scroll: pauses when user scrolls up during streaming
- [x] Admin Sessions: company and frontend origin columns, horizontal scroll
- [x] Admin Frontends: editable frontend names
- [x] Frontend origin stored in session metadata

#### Acceptance Criteria
- [x] "End Session" button visible in chat (red border styling)
- [x] Click → confirmation → summary streams to chat
- [x] Summary saved to `summary.md` on disk
- [x] Session marked `completed` in session.json
- [x] Chat input disabled after session ends
- [x] Summary uses inference LLM (not summariser) per spec §3.6
- [x] Summary generated in session language

---

### Sprint 8d — Report + Internal UNI Summary (DONE)

**Goal:** Background generation of internal UNI summary and report after session closure.

**Depends on:** Sprint 8c (End Session flow)

#### Deliverables
- [x] After user summary: generate internal UNI summary using `session_summary_uni.md` prompt
  - Severity assessment, applicable frameworks
  - Session integrity flag: normal / low_concern / high_concern
  - Recommended priority for UNI attention
- [x] Internal UNI summary saved as `/app/data/sessions/{token}/internal_summary.md`
- [x] Generate report using `internal_case_file.md` prompt + full conversation
- [x] Report saved as `/app/data/sessions/{token}/report.md`
- [x] Report skipped for "training" mode sessions
- [x] Phase-based prompt loading: document prompts REPLACE conversational system prompt
- [x] Both documents generated sequentially after user summary completes
- [x] User does NOT see internal documents (background only)

#### Acceptance Criteria
- [x] After "End Session": summary (visible) → internal UNI summary (background) → report (background)
- [x] `internal_summary.md` contains severity, integrity flag, priority
- [x] `report.md` contains structured case documentation
- [x] Training mode sessions: report skipped, internal summary still generated
- [x] Documents use inference LLM with dedicated prompts (not conversational prompt)
- [x] Full conversation passed as input (not just summary)
- [x] Backend logs confirm document generation

---

### Sprint 8e — Admin Session Enhancements (DONE)

**Goal:** Admin can view generated documents and trigger generation on demand.

**Depends on:** Sprint 8d (report generation)

#### Deliverables
- [x] Sessions list: document status indicators (✓/✗ for summary, internal_summary, report)
- [x] Backend `list_sessions`: check disk for `summary.md`, `internal_summary.md`, `report.md` per session
- [x] Session detail: 3 document sections (Summary, Internal UNI Summary, Report) with content
- [x] Backend endpoints to read documents: `GET /admin/sessions/{token}/documents`
- [x] "Generate" buttons per document — triggers generation on demand for any session
- [x] Backend endpoints to trigger generation: `POST /admin/sessions/{token}/generate/{doc_type}`
- [x] Re-generation overwrites previous file on disk
- [x] Useful for: abandoned sessions (no End Session), re-generation after prompt updates

#### Acceptance Criteria
- [x] Sessions table shows ✓/✗ indicators for each document type
- [x] Session detail displays document content with markdown rendering
- [x] Admin can trigger summary/internal_summary/report generation independently
- [x] Generation works for any session (active or completed)
- [x] Re-generation overwrites previous file
- [x] Documents rendered with markdown in admin panel

---

### Sprint 8f — Inactivity Timeout + Auto-Cleanup (DONE)

**Goal:** Sessions auto-close after configurable inactivity period with automatic document generation. Old sessions auto-removed from backend listing (files preserved on disk). Settings per frontend.

**Depends on:** Sprint 8e (admin documents), Sprint 8d (report generation pipeline)

#### Part 1: Admin Settings UI (Sessions tab)

- [x] New "Session Lifecycle" settings panel in Sessions tab (collapsible)
- [x] Per-frontend configuration (button selector for each registered frontend)
- [x] **Auto-closure:** toggle on/off + timeout in hours (default: 2h, range 1-48h)
- [x] **Auto-cleanup:** toggle on/off + retention period in days (default: 30d, range 1-365d)
- [x] Settings persisted to `/app/data/session_lifecycle.json` (per frontend_id)
- [x] Backend endpoints: `GET /admin/sessions/lifecycle` and `PUT /admin/sessions/lifecycle/{frontend_id}`

#### Part 2: Background Scanner

- [x] `services/session_lifecycle.py` — asyncio background task, runs every 5 minutes
- [x] Scan active sessions: if `last_activity` exceeds frontend's auto-closure timeout → trigger closure
- [x] Auto-closure generates all 3 documents (summary, internal_summary, report) without streaming
  - Uses same `_generate_document()` from polling.py
  - Summary NOT streamed (user is gone) — saved directly to disk
  - Report skipped for training mode (same logic as manual closure)
- [x] Mark session `completed` after document generation
- [x] Scan completed sessions: if `last_activity` exceeds frontend's retention period → remove from store
- [x] "Remove from store" = delete from in-memory cache + mark `archived: true` in session.json
  - Files on disk (session.json, conversation.jsonl, documents) are NEVER deleted
  - Session no longer appears in admin list or counts
- [x] Log auto-closure and auto-cleanup events with session token

#### Part 3: Backend Integration

- [x] Start background task on backend startup (`main.py` lifespan)
- [x] Session store: `archive_session(token)` method — removes from cache, marks archived in session.json
- [x] `_ensure_loaded()` skips archived sessions
- [x] `frontend_id` stored in session metadata for lifecycle mapping
- [x] Sessions without a known frontend use global defaults (both features off)

#### Acceptance Criteria
- [x] Admin Sessions tab shows lifecycle settings panel with per-frontend config
- [x] Auto-closure toggle + timeout configurable per frontend
- [x] Auto-cleanup toggle + retention configurable per frontend
- [x] Session inactive for configured timeout → auto-closed with documents generated
- [x] Session older than retention period → removed from admin list
- [x] Archived session files remain on disk (volume)
- [x] Active sessions not affected by scanner
- [x] Multiple sessions can be processed in same scan cycle
- [x] Settings persist across backend restart
- [x] Backend logs auto-closure and auto-cleanup events

---

### Sprint 8g — Evidence Document Upload (DONE)

**Goal:** Users can upload documents during session. Summariser processes them for safe context injection.

**Depends on:** Sprint 8a (disk persistence)

#### Part 1: Sidecar Upload Endpoint

- [x] `POST /internal/upload/{session_token}` — accepts file via multipart form
- [x] Validates: size ≤ 25MB, allowed extensions (.pdf, .txt, .md, .doc, .docx, .jpg, .png)
- [x] Stores file temporarily in sidecar memory/tmpdir
- [x] Adds upload notification to message queue (type: `upload`, includes filename + session_token)
- [x] `GET /internal/upload/{session_token}/{filename}` — backend fetches the file
- [x] `DELETE /internal/upload/{session_token}/{filename}` — backend confirms receipt, sidecar deletes temp file
- [x] Sidecar never keeps files permanently — cleaned up after backend fetches

#### Part 2: Backend Upload Processing

- [x] Polling loop detects `upload` type messages in queue
- [x] Fetches file from sidecar via GET, saves to `/app/data/sessions/{token}/evidence/`
- [x] Confirms receipt (DELETE on sidecar — sidecar deletes temp copy)
- [x] **Text files** (.txt, .md, .pdf, .doc, .docx):
  - Extracts text content (LlamaIndex readers for pdf/docx)
  - Sends to summariser LLM with dedicated prompt → concise structured summary
  - Summary saved to `/app/data/sessions/{token}/evidence/{filename}.summary.md`
  - Summary injected as fixed system context (model always knows what was uploaded)
  - Full text indexed in **session-specific RAG** (LlamaIndex in-memory index per token)
- [x] **Images** (.jpg, .png):
  - Stored in evidence folder (added to dossier) but NOT analyzed
  - Model informed that an image was uploaded but cannot be processed
- [x] `prompts/evidence_summary.md` — dedicated prompt for document summarisation
- [x] Session RAG index discarded when session is archived/backend restarts (originals on disk)

#### Part 3: Frontend UI

- [x] Upload button in ChatShell (paperclip icon, next to send button, mobile-compatible `<input type="file">`)
- [x] Accepted types filter in file picker (accept attribute)
- [x] Upload progress indicator (uploading... → processing... → done)
- [x] SSE events for upload status: `upload_received`, `upload_processed`, `upload_error`
- [x] On `upload_processed`: brief assistant-style notification in chat ("Document received and analyzed")
- [x] On image upload: notification that image was stored but not analyzed
- [x] Disclaimer in instructions: "You can upload documents during the chat. Text documents will be analyzed. Images will be stored but cannot be analyzed by the system."
- [x] i18n for upload-related strings (EN/ES minimum, others English fallback)

#### Part 4: Context Integration

- [x] `polling.py`: inject evidence summaries as system context before inference
- [x] Session RAG: query per-session index alongside global RAG, merge chunks
- [x] Evidence context format: "Documents uploaded by user:\n- {filename}: {summary}\n..."
- [x] Multiple uploads supported per session (summaries accumulate)
- [x] Evidence summaries saved to session disk (`evidence_context.json`) for recovery

#### Acceptance Criteria
- [x] Upload button visible in chat, works on mobile (iOS Safari, Android Chrome)
- [x] Text documents: summarised + indexed for session RAG
- [x] Images: stored in evidence, model informed but no analysis
- [x] File uploaded → processing indicator → confirmation in chat
- [x] Summariser processes content (not raw injection — prevents prompt injection)
- [x] Session RAG allows model to query document details during conversation
- [x] Evidence summaries persist as fixed context (survive compression)
- [x] Original files persist in `/app/data/sessions/{token}/evidence/`
- [x] Sidecar deletes temp files after backend confirms receipt
- [x] 25MB size limit enforced
- [x] Disclaimer about image limitations shown to user

---

### Sprint 8g-b — Batch Document Upload + UX Polish (DONE)

**Goal:** Users can upload up to 4 documents at once. Processing indicator as assistant bubble. Single LLM response for batch.

**Depends on:** Sprint 8g (single upload)

#### Part 1: Frontend — Multi-file Selection + UX

- [x] `<input type="file" multiple>` — allow selecting multiple files at once
- [x] Client-side limit: max 4 files per batch. If >4, show error and reject
- [x] Upload loop: POST each file individually to sidecar (reuse existing endpoint)
- [x] Upload status shows progress: "Uploading 1/3...", "Uploading 2/3...", etc.
- [x] Processing indicator as assistant bubble (same style as "Processing..." for messages) with pulse animation
- [x] Message: "Processing document. This may take a minute — please don't leave the page."
- [x] Indicator visible from upload_processed until LLM response (done event)
- [x] i18n: `upload_batch_progress`, `upload_batch_limit`, `upload_analyzing` (EN/ES)

#### Part 2: Backend — Batch Processing + Single Response

- [x] `poll_frontends()`: group uploads by `session_token` before processing
- [x] `_handle_upload()` returns result instead of triggering response
- [x] `_respond_to_upload()` accepts list of results, builds batch-aware message
- [x] Single LLM response for all files in batch using inference model
- [x] Each file still gets individual `upload_processed` SSE event
- [x] Mixed batches (text + images) handled: text summarised, images noted

#### Acceptance Criteria
- [x] User can select 1-4 files in file picker
- [x] >4 files → error message, upload rejected
- [x] Progress indicator shows file-by-file upload status
- [x] Assistant bubble with pulse shows processing status
- [x] Single LLM response after entire batch is processed
- [x] Auto-response references all documents in batch
- [x] Mixed text+image batches handled correctly

---

### Sprint 8h — Campaign-Specific Prompts & RAG (DONE)

**Goal:** Per-frontend prompt sets and RAG document collections for parallel campaigns.

**Depends on:** Sprint 8a (disk persistence), Sprint 7a (RAG service), Sprint 8f (frontend_id in sessions)

**Idea source:** `docs/ideas.md` — "Campañas paralelas: prompts y RAG por frontend"

#### Part 1: Per-Frontend Prompts (Toggle Mode: Global / Per Frontend)

Toggle at top of Prompts tab controls the mode:

- **Global** (default): single prompt set, applies to all frontends. Current behavior.
- **Per Frontend**: each frontend gets its own prompt set. Global prompts are ignored.

When switching Global → Per Frontend:
- All global prompts are copied to each registered frontend that doesn't already have custom prompts
- Each frontend starts as a copy of global, admin can then customize per frontend

When switching Per Frontend → Global:
- Frontend-specific prompts stay on disk (not deleted) but are ignored
- All frontends use global prompts again

- [x] Prompt mode config: `/app/data/prompt_mode.json` — `{ "mode": "global" | "per_frontend" }`
- [x] `prompt_assembler.py` — accept `frontend_id`, check mode:
  - `global` → load from `/app/data/prompts/` (current behavior)
  - `per_frontend` → load from `/app/data/campaigns/{frontend_id}/prompts/`
- [x] Prompt storage per frontend: `/app/data/campaigns/{frontend_id}/prompts/`
- [x] Admin Prompts tab UI:
  - Toggle "Global / Per Frontend" at top
  - Global mode = current editor (unchanged)
  - Per Frontend mode = frontend selector tabs/dropdown + prompt editor scoped to selected frontend
  - Auto-copy from global when activating Per Frontend mode (for frontends without existing prompts)
- [x] Backend prompt endpoints: accept optional `?frontend_id=` query param (used in Per Frontend mode)
- [x] `polling.py` — pass `frontend_id` to `assemble_system_prompt()`

#### Part 2: Per-Frontend RAG (Additive Model)

RAG is always additive. Global RAG panel stays. Each frontend can have its own documents AND toggle whether to also include global RAG.

- [x] RAG storage: `/app/data/campaigns/{frontend_id}/documents/` + `/app/data/campaigns/{frontend_id}/rag_index/`
- [x] `rag_service.py` — per-campaign index (cached in-memory like global)
  - `get_relevant_chunks(query, top_k, frontend_id)` → queries campaign index + optionally global
  - `index_campaign(frontend_id)` — build index from campaign docs
  - `add_campaign_document(frontend_id, ...)` / `remove_campaign_document(frontend_id, ...)`
- [x] Campaign RAG config: `/app/data/campaigns/{frontend_id}/rag_config.json`
  - `include_global_rag: true` (default) — per frontend toggle
- [x] Admin RAG tab UI:
  - Global RAG section stays at top (current behavior, always visible)
  - Below: collapsible "Campaign Documents" section per registered frontend
  - Each frontend section: document list + upload/delete + "Include Global RAG" toggle + Reindex
  - Frontends without campaign docs show empty state with upload button
- [x] Backend RAG endpoints: accept optional `?frontend_id=` query param
- [x] `polling.py` — pass `frontend_id` to `get_relevant_chunks()`

#### Part 3: Backend Integration

- [x] `frontend_id` already available in polling loop (from frontend registry)
- [x] `frontend_id` already stored in `session.json` (from Sprint 8f)
- [x] Campaign directory auto-created on first upload or prompt copy
- [x] Deleting a frontend from admin does NOT delete campaign data (files preserved on disk)
- [x] When a new frontend is registered and prompt mode is `per_frontend` → auto-copy global prompts

#### Part 4: Admin UI

- [x] Prompts tab: mode toggle + conditional UI (global editor vs. frontend selector + scoped editor)
- [x] RAG tab: global section (unchanged) + campaign sections per frontend (collapsible)
- [x] Visual indicator when a frontend has campaign documents (count badge)

#### Acceptance Criteria
- [ ] Prompts toggle "Global / Per Frontend" works and persists
- [ ] Global mode: all frontends use same prompts (current behavior, no regression)
- [ ] Per Frontend mode: each frontend has its own prompt set
- [ ] Switching to Per Frontend auto-copies global prompts to frontends without custom sets
- [ ] Switching back to Global ignores frontend prompts (but doesn't delete them)
- [ ] Admin can edit prompts per frontend in Per Frontend mode
- [ ] Admin can upload campaign-specific RAG documents per frontend
- [ ] Campaign docs indexed in separate LlamaIndex index per frontend
- [ ] "Include Global RAG" toggle per frontend controls global chunk inclusion
- [ ] Default: include global RAG = true (new frontends get global + campaign)
- [ ] Sessions on a frontend receive correct prompts (global or frontend-specific)
- [ ] Sessions on a frontend receive correct RAG (campaign + optionally global)
- [ ] Campaign docs don't leak to other frontends
- [ ] Documents and prompts persist across container restarts
- [ ] Reindex works per campaign and globally
- [ ] Removing a frontend does NOT delete its campaign data from disk
- [ ] New frontend registered in Per Frontend mode → gets global prompts copied automatically

---

### Sprint 9 — SMTP Integration + Email Auth + Guardrails + Production Prompts (DONE)

**Goal:** Email service for auth codes, report forwarding, and admin notifications. Everything disableable — system works fully without SMTP.

**Depends on:** Sprint 8c (session closure), Sprint 8d (reports), Sprint 6 (SMTP tab stub)

**Design decisions (from discussion with Daniel):**
- SMTP is best-effort: failure never blocks the user flow (except auth — see below)
- Auth bypass via `auth_required: false` in deployment config (editable via Portainer)
- Email whitelist managed in backend admin panel
- Metrics/abuse detection deferred to backlog
- Email format: text with markdown content
- Language: admin emails in English, user emails in session language
- Gmail SMTP for testing (smtp.gmail.com:587, app password)

#### Part 1: SMTP Service

- [x] `services/smtp_service.py` — async email sending with aiosmtplib
  - `send_email(to, subject, body)` — basic send function (best-effort, never raises)
  - `test_connection()` — tests SMTP + optionally sends test email
  - `check_smtp_health()` — non-blocking startup health check
  - TLS support (Gmail compatible)
- [x] Admin SMTP tab: "Test Connection" wired to real test endpoint
- [x] SMTP master toggle: if host is empty, all email features silently skip
- [x] Add `aiosmtplib>=3.0` to backend requirements.txt
- [x] SMTP health check on startup (non-blocking, logs warning if unreachable)

#### Part 2: Email Authentication (Organizer)

- [x] **Email whitelist** in backend admin:
  - Authorized emails section in SMTP tab
  - Add/remove email addresses
  - Stored in `/app/data/authorized_emails.json`
  - Backend endpoints: `GET/PUT /admin/smtp/authorized-emails`
- [x] **Auth flow via pull-inverse:**
  - Frontend `AuthPage.tsx` → POST email to sidecar → backend polls
  - Backend checks whitelist → if not found, rejects with "not authorized"
  - Backend generates 6-digit code, stores with 10-min expiry (in-memory)
  - Backend sends code via SMTP to the email
  - Frontend shows code input → POST code to sidecar → backend verifies
  - On success: backend pushes verification result to sidecar → frontend proceeds
- [x] **Sidecar endpoints:**
  - `POST /internal/auth/request-code` — request auth code
  - `POST /internal/auth/verify-code` — submit code for verification
  - `GET /internal/auth/status/{session_token}` — frontend polls for result
  - `POST /internal/auth/{session_token}/result` — backend pushes result
  - Auth requests included in `GET /internal/queue` response for backend polling
- [x] **Auth bypass:** `auth_required: false` in deployment config → auth phase skipped
- [x] **Backend auth handler:** `_handle_auth_request()` in polling.py
  - Whitelist check → code generation → SMTP send → result push to sidecar
  - Code verification → result push to sidecar
- [x] **SMTP failure handling:**
  - Poll-based with 30s timeout (not retry button — cleaner UX)
  - Clear error messages per status (not_authorized, smtp_error, timeout, invalid_code)
  - After 3 failed code attempts: "Contact administrator" message, input disabled
  - Backend logs all SMTP errors
- [x] **i18n:** auth error messages in EN/ES/FR + English fallback for all other languages

#### Part 3: Notification Toggles (Admin SMTP Tab)

- [x] SMTP config expanded with notification toggles:
  - `notify_on_report: bool` — email admin on report generation (default: false)
  - `send_summary_to_user: bool` — email summary to user (default: false)
  - `send_report_to_user: bool` — email report to user (default: false)
- [x] Admin SMTP tab: "Email Notifications" section with descriptive toggles
- [x] Integration in `_generate_internal_documents()` (polling.py):
  - After report generation: check toggles → send if enabled
  - User emails only sent if email in authorized_emails
  - User emails in session language, admin emails in English
- [x] `smtp_service.py` notification functions:
  - `notify_admin_report()` — admin notification with report content
  - `send_user_summary()` — session summary to user (multi-language)
  - `send_user_report()` — report to user (multi-language)

#### Part 4: Frontend Auth Flow (Wire Up)

- [x] `AuthPage.tsx` — real sidecar calls:
  - POST email to `/internal/auth/request-code`
  - Poll `/internal/auth/status/{session_token}` for result
  - Handle: code_sent, verified, invalid_code, not_authorized, smtp_error, timeout states
  - Max 3 code verification attempts, then disabled + "contact admin"
  - "Code sent to [email]" confirmation message
- [x] Store verified email in session (passed to backend with survey)

#### Acceptance Criteria
- [x] SMTP sends emails via aiosmtplib (Gmail or any SMTP server)
- [x] "Test Connection" sends real test email to admin address
- [x] System works fully without SMTP configured (all email features silently skip)
- [x] Organizer auth: email → whitelist check → code sent → code verified → proceed
- [x] Non-whitelisted email → clear rejection message
- [x] `auth_required: false` → auth phase skipped entirely
- [x] SMTP failure during auth → clear error, 3-attempt limit
- [x] SMTP health checked on startup (warning log if unreachable, non-blocking)
- [x] Admin toggle: notify on report → email sent to admin
- [x] Admin toggle: send summary/report to user → email sent to user (organizer only)
- [x] User emails in session language, admin emails in English
- [x] Notification toggles persist in smtp_config.json
- [x] Authorized emails list managed from admin panel
- [x] All email sending is best-effort (failure logged, never crashes system)
- [x] Verified email stored in session for notifications

---

### Sprint 10 — Guardrails de Código + Detección de Repetición + Polish

**Goal:** Pre-LLM content filter, model repetition detection, loose ends, code audit. Commit after Blocks 1-3, then Block 4 audit.

#### Block 1: Pre-LLM Content Filter (Hardcoded Guardrails)

Spec §13.1 — The guardrails prompt layer (Sprint 9) instructs the LLM, but this is the **code-level safety net** that runs BEFORE the LLM call. Fixed responses are NOT generated by the model — they're hardcoded strings returned directly.

- [x] `services/guardrails.py` — Pre-inference content filter
  - Keyword/pattern detection: hate speech, discriminatory content, prompt injection attempts
  - Pattern categories: slurs, dehumanizing language, role override ("ignore your instructions", "you are now..."), system prompt probing
  - Returns fixed response string in session language (hardcoded, NOT LLM-generated)
  - Fixed responses in EN/ES/FR/DE/PT/IT with proper translations, others English fallback (full translations in dedicated translation sprint, see ideas.md)
  - Violation counter per session (persisted in session.json)
  - After `guardrail_max_triggers` (default: 3) consecutive violations → session flagged + ended gracefully
- [x] Integration in `polling.py`: check BEFORE LLM call
  - If triggered → push fixed response to stream, skip inference entirely
  - Increment violation counter
  - If threshold reached → flag session, push closure message, mark completed
- [x] Config: `guardrails_enabled` and `guardrail_max_triggers` already in `deployment_backend.json`
- [x] Admin visibility: flagged sessions show guardrail trigger count

#### Block 2: Model Repetition Detection

The LLM occasionally enters generation loops (repeating phrases/paragraphs). Detection must be conservative — cutting a legitimate response is worse than letting a repetition run a bit long.

- [x] `services/repetition_detector.py` — Streaming repetition analysis
  - Sliding window n-gram comparison on accumulated output
  - Conservative thresholds: only trigger on clear repetition loops (3+ repetitions of 40+ char phrases)
  - Returns signal to stop generation when loop detected
- [x] Integration in `polling.py`: wrapper around LLM streaming
  - Feed each chunk to detector
  - If loop detected → stop streaming, send accumulated text up to repetition point
  - Log the event with session token and repeated content
- [x] **Documentation:** Clear comments explaining thresholds and why they're set conservatively. False positives (cutting legitimate responses) are much worse than false negatives (letting some repetition through). Better to miss a loop than to cut a valid response.
- [x] Testing: thresholds validated with examples (25+ char phrases cover typical loops, conservative enough for legitimate lists/frameworks)

#### Block 3: Sprint 8h Loose End

- [x] Auto-copy global prompts when registering a new frontend in `per_frontend` prompt mode
  - Check prompt mode on frontend registration
  - If `per_frontend` → copy global prompts to new frontend's campaign directory

**>>> COMMIT CHECKPOINT after Blocks 1-3 <<<**

#### Block 4: Code Audit & Polish

- [x] Error handling audit: scan all services for unhandled exceptions, missing try-except
  - SMTP config load wrapped in try-except (crash on empty/corrupt JSON)
  - poll_frontends() AsyncClient wrapped in try/finally (resource leak)
  - _send_queue_positions() converted to async with (resource leak)
  - _finalize_session prompt read with fallback (FileNotFoundError)
  - _generate_document prompt read with try-except (FileNotFoundError)
  - context_compressor JSON response parsing with specific exceptions
- [x] Log review: ensure errors are logged with enough context, no silent failures
  - rag_service: silent `except: pass` replaced with logged warnings
  - admin smtp _load_config: silent failure now caught
- [x] Dead code cleanup: remove unused imports, commented-out code, stale TODOs
  - Removed `import time` from session_store.py (unused)
  - Deleted session_history.py (replaced by session_store.py in Sprint 8a)
- [x] Edge case review: empty sessions, missing files, corrupt JSON, concurrent access
  - All file writes in polling.py converted to atomic tmp+rename pattern
  - session_lifecycle.py auto-close write converted to atomic
  - admin smtp _save_config: parent dir creation added
  - Race conditions: low risk (processing is sequential) — documented, not fixed
- [x] Verify all Docker volumes and persistence paths are correct

#### Acceptance Criteria
- [x] Hate speech / discriminatory content → fixed hardcoded response (not LLM)
- [x] Prompt injection attempts → same fixed response
- [x] 3 violations → session flagged and ended
- [x] Guardrail response in session language (EN/ES/FR/DE/PT/IT, English fallback for others)
- [x] `guardrails_enabled: false` → filter skipped entirely
- [x] Model repetition loop → generation stopped, partial response delivered
- [x] Repetition detector conservative thresholds (25 char phrases, 3+ repetitions, 200+ chars accumulated)
- [x] New frontend in per_frontend mode → gets global prompts copied
- [x] No unhandled exceptions in backend services (audit complete)
- [x] All error paths logged with context

---

### What's Next
- **Prompt quality testing phase:** Deep testing of production prompts across all profiles/cases with real scenarios
- **Translation sprint:** Complete i18n for all 31 languages (frontend user-facing text + guardrail responses)
- **Sprint 11:** Production deployment + cross-machine testing
- **Sprint 12:** Letta/MemGPT integration (experimental)

---

## Previous Version (v1) History

v1 was developed from Sprint 8 through Sprint 11f. The chat flow worked in Sprint 11a but regressed in later sprints. A bisection effort was underway but the codebase had accumulated enough technical debt to warrant a clean rewrite.

Key lessons from v1 are documented in `docs/knowledge/lessons-learned.md`.
