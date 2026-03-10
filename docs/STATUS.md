# HRDD Helper — Project Status

**Last Updated:** 2026-03-09

## Current State: v2 Rewrite — Sprint 7c Complete

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

### Sprint 8b — Session Recovery (PLANNED)

**Goal:** Users can resume sessions by entering their token. Recovery skips role select, instructions, and survey.

**Depends on:** Sprint 8a (disk persistence)

#### Deliverables
- [ ] Sidecar endpoint: `GET /internal/session/{token}/recover` → returns session data or 404
  - Backend must have pushed session data to sidecar, OR sidecar queries backend
  - Decision: sidecar forwards to backend via poll response (pull-inverse compatible)
  - Alternative: backend pushes session metadata to sidecar when session is initialized
- [ ] Backend endpoint: session recovery data (survey, language, role, mode, message count, status)
- [ ] Frontend `App.tsx`: on recover → fetch session data → restore language, role, survey → skip to chat
- [ ] Frontend `SessionPage.tsx`: show error if token not found or expired
- [ ] Resume window enforcement: 48h worker, 120h organizer (from `deployment config`)
- [ ] Expired token → clear error message with window duration
- [ ] Recovered session loads conversation history into chat UI

#### Acceptance Criteria
- [ ] Enter valid token → chat resumes with previous conversation visible
- [ ] Language, role, survey data restored (no re-entry)
- [ ] Recovery skips: role select, instructions, survey (go straight to chat)
- [ ] Expired token (>48h worker / >120h organizer) → error message
- [ ] Invalid token → error message
- [ ] Works on both frontworker and frontorganizer
- [ ] Pull-inverse architecture respected (frontend doesn't call backend directly)

---

### Sprint 8c — End Session + Summary (PLANNED)

**Goal:** User can end session. Summary is generated and streamed to chat as final message.

**Depends on:** Sprint 8a (disk persistence)

#### Deliverables
- [ ] "End Session" button in ChatShell (red border, per spec §3.5)
- [ ] Frontend sends `finalize: true` in message payload (spec §8.1)
- [ ] Backend detects `finalize` flag in polling
- [ ] Summary generation: load `session_summary.md` prompt + full conversation → LLM inference
- [ ] Summary streamed to chat as final assistant message (user sees it)
- [ ] Summary saved as `/app/data/sessions/{token}/summary.md`
- [ ] Session status set to `completed`
- [ ] Chat input disabled after finalization
- [ ] Confirmation dialog before ending ("Are you sure?")

#### Acceptance Criteria
- [ ] "End Session" button visible in chat (red border styling)
- [ ] Click → confirmation → summary streams to chat
- [ ] Summary saved to `summary.md` on disk
- [ ] Session marked `completed` in session.json
- [ ] Chat input disabled after session ends
- [ ] Summary uses inference LLM (not summariser) per spec §3.6
- [ ] Summary generated in session language

---

### Sprint 8d — Report + Internal Assessment (PLANNED)

**Goal:** Background generation of internal report and UNI assessment after session closure.

**Depends on:** Sprint 8c (End Session flow)

#### Deliverables
- [ ] After summary: generate report using `internal_case_file.md` prompt + full conversation
- [ ] Report saved as `/app/data/sessions/{token}/report.md`
- [ ] Report skipped for "training" mode sessions (spec §3.6)
- [ ] Internal assessment using dedicated prompt + full conversation (spec §13.3)
  - Severity assessment, applicable frameworks
  - Session integrity flag: normal / low_concern / high_concern
  - Recommended priority for UNI attention
- [ ] Assessment saved as `/app/data/sessions/{token}/internal_assessment.md`
- [ ] Phase-based prompt loading (spec §13.4): report/assessment prompts REPLACE conversational prompt
- [ ] Both report and assessment generated sequentially after summary completes
- [ ] User does NOT see report or assessment (background only)

#### Acceptance Criteria
- [ ] After "End Session": summary (visible) → report (background) → assessment (background)
- [ ] `report.md` contains structured case documentation
- [ ] `internal_assessment.md` contains severity, integrity flag, priority
- [ ] Training mode sessions: report skipped, assessment still generated
- [ ] Report/assessment use inference LLM with dedicated prompts (not conversational prompt)
- [ ] Full conversation passed as input (not just summary)
- [ ] Admin can view report and assessment in session detail

---

### Sprint 8e — Admin Session Enhancements (PLANNED)

**Goal:** Admin panel shows report status and can trigger generation on demand.

**Depends on:** Sprint 8d (report generation)

#### Deliverables
- [ ] Sessions list: status column (active/completed/flagged)
- [ ] Sessions list: report status indicators (checkmarks for summary/report/assessment)
- [ ] Session detail: display summary, report, and assessment as tabs or sections
- [ ] "Generate Summary" button — triggers on demand for any session
- [ ] "Generate Report" button — triggers on demand for any session
- [ ] "Generate Assessment" button — triggers on demand for any session
- [ ] Useful for: abandoned sessions, re-generation with updated prompts
- [ ] Session filters: All, Active, Completed, Flagged (currently only All/Flagged)

#### Acceptance Criteria
- [ ] Status indicators visible: ✓ summary, ✓ report, ✓ assessment (or ✗ if missing)
- [ ] Admin can trigger any generation independently
- [ ] Re-generation overwrites previous file
- [ ] Filters work correctly (Active shows only active, etc.)
- [ ] Report/assessment content readable in admin panel

---

### Sprint 8f — Inactivity Timeout (PLANNED)

**Goal:** Sessions auto-close after configurable inactivity period. Reports generated automatically.

**Depends on:** Sprint 8d (report generation pipeline)

#### Deliverables
- [ ] Backend background task: scan active sessions for inactivity
- [ ] Configurable timeout (default 2h, in deployment config)
- [ ] Auto-trigger closure flow: summary → report → assessment → mark completed
- [ ] User is no longer present — summary saved but not streamed
- [ ] Scan interval: every 5 minutes (configurable)
- [ ] Log when session is auto-closed

#### Acceptance Criteria
- [ ] Session with no activity for 2h → auto-closed
- [ ] Summary + report + assessment generated automatically
- [ ] Session marked `completed` in admin
- [ ] Active sessions NOT affected
- [ ] Timeout configurable in backend deployment config
- [ ] Multiple sessions can be auto-closed in same scan

---

### Sprint 8g — Evidence Document Upload (PLANNED)

**Goal:** Users can upload documents during session. Summariser processes them for safe context injection.

**Depends on:** Sprint 8a (disk persistence)

#### Deliverables
- [ ] File input button in ChatShell (📎 or similar, mobile-compatible `<input type="file">`)
- [ ] Supported formats: .pdf, .txt, .md, .doc, .docx, .jpg, .png (images OCR TBD)
- [ ] File upload via sidecar: `POST /internal/upload/{session_token}`
- [ ] Backend fetches uploaded file during polling
- [ ] Security: summariser reviews document content (not raw injection — prevents prompt injection)
- [ ] Summariser generates structured summary of document
- [ ] Summary injected as fixed context in conversation
- [ ] Original file stored in `/app/data/sessions/{token}/evidence/`
- [ ] Document summary stored alongside for reference
- [ ] Size limit: 25MB per file (spec §13)

#### Acceptance Criteria
- [ ] Upload button visible in chat (doesn't leave SPA on mobile)
- [ ] File uploaded → processing indicator shown
- [ ] Summariser extracts key information from document
- [ ] Summary added to conversation context (LLM can reference it)
- [ ] Raw document content never passed directly to inference LLM
- [ ] Original files persist in session directory
- [ ] Upload works on mobile browsers (iOS Safari, Android Chrome)

---

### Sprint 8h — Campaign-Specific RAG (PLANNED)

**Goal:** Campaign documents attached to specific frontend deployments.

**Depends on:** Sprint 8a (disk persistence), Sprint 7a (RAG service)

#### Deliverables
- [ ] Campaign documents tied to specific frontend IDs in backend
- [ ] Admin RAG tab: frontend selector to assign documents per deployment
- [ ] Campaign RAG injected alongside global RAG for sessions on that frontend
- [ ] Frontend-specific document management (upload/delete per frontend)
- [ ] Campaign documents stored in `/app/data/campaigns/{frontend_id}/`
- [ ] Separate LlamaIndex index per campaign

#### Acceptance Criteria
- [ ] Admin can assign documents to a specific frontend
- [ ] Sessions on that frontend receive campaign-specific RAG context
- [ ] Global RAG documents still apply to all frontends
- [ ] Campaign docs don't leak to other frontends
- [ ] Documents persist across container restarts
- [ ] Reindex works per campaign

---

### What's Needed After Sprint 8
- **Sprint 9:** SMTP integration (auth codes, report forwarding, admin notifications)
- **Sprint 10:** Ethical guardrails + content safety
- **Sprint 11:** Polish + production deployment + repetition detection
- **Sprint 12:** Letta/MemGPT integration (experimental)

---

## Previous Version (v1) History

v1 was developed from Sprint 8 through Sprint 11f. The chat flow worked in Sprint 11a but regressed in later sprints. A bisection effort was underway but the codebase had accumulated enough technical debt to warrant a clean rewrite.

Key lessons from v1 are documented in `docs/knowledge/lessons-learned.md`.
