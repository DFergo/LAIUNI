# HRDD Helper v2 — Sprint Milestones & Acceptance Criteria

**Spec reference:** `docs/SPEC-v2.md`
**Status tracking:** `docs/STATUS.md`

Each sprint has explicit acceptance criteria. A sprint is NOT done until ALL criteria pass.

---

## Sprint 1 — Project Scaffolding

**Goal:** Both containers build and run (empty shells)

### Deliverables
- [ ] `Dockerfile.backend` — Python 3.11 + FastAPI
- [ ] `Dockerfile.frontend` — Node 20 + Nginx + Python sidecar
- [ ] `docker-compose.backend.yml` — port 8000, hrdd-data volume
- [ ] `docker-compose.frontworker.yml` — port 8091, hrdd-fw-data volume
- [ ] `docker-compose.frontorganizer.yml` — port 8090, hrdd-fo-data volume
- [ ] `src/backend/main.py` — FastAPI app with health endpoint
- [ ] `src/backend/requirements.txt` — dependencies
- [ ] `src/frontend/package.json` — React + Vite + Tailwind
- [ ] `src/frontend/tailwind.config.js` — UNI colors configured
- [ ] `src/frontend/vite.config.ts`
- [ ] `src/frontend/src/App.tsx` — "Hello HRDD" placeholder
- [ ] `config/nginx/frontend.conf` — with SSE headers

### Acceptance Criteria
- [ ] `docker compose -f docker-compose.backend.yml build` succeeds
- [ ] `docker compose -f docker-compose.frontworker.yml build` succeeds
- [ ] Backend responds to `GET http://localhost:8000/health` → `{"status": "ok"}`
- [ ] Frontend loads React app at `http://localhost:8091`
- [ ] Frontend Nginx proxies `/internal/` to sidecar (returns 404, not 502)
- [ ] Data directories exist inside containers at `/app/data`

### Spec Sections Covered
- §2.1 (Containers), §2.2 (Frontend Container), §2.3 (Backend Container)
- §2.5 (Nginx Configuration), §5 (Visual Design — Tailwind config only)
- §10 (Docker Compose Files)

---

## Sprint 2 — Backend Core (Admin Auth + Config)

**Goal:** Backend admin login works. Config loader ready.

### Deliverables
- [ ] `src/backend/core/config.py` — Pydantic config loader (BackendConfig, FrontendConfig)
- [ ] `src/backend/api/v1/admin/auth.py` — Setup, login, JWT
- [ ] Admin React app (minimal): login page + "Welcome" dashboard
- [ ] First-run flow: create password → hash to `/app/data/.admin_hash`
- [ ] JWT auth with configurable expiry + "remember me"
- [ ] Backend serves admin app at `/` (root)

### Acceptance Criteria
- [ ] First visit to `http://localhost:8000` shows "Create Admin Account"
- [ ] After creating password, shows login form
- [ ] Login returns JWT, redirects to admin dashboard
- [ ] Invalid password shows error message
- [ ] JWT persists across page reloads (stored in localStorage)
- [ ] "Remember me" extends JWT expiry
- [ ] `deployment_backend.json` loaded and validated by Pydantic
- [ ] Deleting `.admin_hash` resets to first-run setup

### Spec Sections Covered
- §4.1 (Authentication), §9.1 (Backend Config)
- §2.3 (Backend landing = admin login)

---

## Sprint 3 — Frontend User Flow (No Chat Yet)

**Goal:** Complete user journey from language selection to survey submission.

### Deliverables
- [ ] `LanguageSelector.tsx` — 16 languages grid
- [ ] `DisclaimerPage.tsx` — purpose + accept button
- [ ] `SessionPage.tsx` — new session (token generation) + recover
- [ ] `AuthPage.tsx` — email verification (organizer only)
- [ ] `SurveyPage.tsx` — role-dependent form fields
- [ ] `ChatShell.tsx` — placeholder (shows "Chat coming soon")
- [ ] `App.tsx` — phase state machine (loading → language → ... → chat)
- [ ] Frontend sidecar: `GET /internal/config` endpoint

### Acceptance Criteria
- [ ] Language selector shows 16 languages in responsive grid
- [ ] Clicking a language → disclaimer page in that language
- [ ] Accept disclaimer → session page
- [ ] "New session" generates `WORD-NUMBER` token and displays it
- [ ] Worker: session → survey (skip auth)
- [ ] Organizer: session → auth → survey
- [ ] Survey shows correct fields per role (see §3.4 matrix)
- [ ] Survey submit → chat placeholder
- [ ] Session recovery: entering valid token loads previous state
- [ ] Colors match: header `#003087`, cards white/rounded-xl, buttons uni-blue
- [ ] Footer shows disclaimer text, hidden during chat phase
- [ ] Sidecar returns correct config per deployment JSON

### Spec Sections Covered
- §3 (Frontend User Flow — all subsections)
- §5 (Visual Design — full implementation)
- §8.5 (FrontendDeploymentConfig)

---

## Sprint 4 — Message Queue + Polling

**Goal:** The pull-inverse pipeline works end-to-end (with mock responses).

### Deliverables
- [ ] Frontend sidecar: `POST /internal/queue` (enqueue user message)
- [ ] Frontend sidecar: `GET /internal/queue` (backend polls, dequeue)
- [ ] Frontend sidecar: `POST /internal/stream/{token}/chunk` (receive response)
- [ ] Frontend sidecar: `GET /internal/stream/{token}` (SSE to React)
- [ ] Backend: `services/polling.py` — background polling loop
- [ ] Backend: `services/message_queue.py` — in-memory queue with TTL
- [ ] Backend: `services/frontend_registry.py` — persistent JSON registry
- [ ] Backend: admin frontends tab (register, discover, enable/disable)
- [ ] `ChatShell.tsx` — real chat with EventSource streaming

### Acceptance Criteria
- [ ] User sends message → appears in frontend sidecar queue
- [ ] Backend polls frontend → receives message → queue is empty after poll
- [ ] Backend sends mock response chunks → frontend receives via SSE
- [ ] React renders tokens in real-time (not batched)
- [ ] SSE events: `token` (individual), `done` (complete text), `error`
- [ ] EventSource onerror unblocks UI after 3 failures (lesson-learned #1)
- [ ] Message TTL: 300s expiry works
- [ ] Frontend registry persists to JSON (atomic write — lesson-learned #5)
- [ ] Admin can register frontend by URL via `/internal/config` discovery
- [ ] Admin can enable/disable frontend polling
- [ ] Both containers on same machine, communicating via HOST IP
- [ ] Chat bubbles: user right/blue, assistant left/white/markdown

### Spec Sections Covered
- §2.4 (Message Flow), §4.2.1 (Frontends Tab)
- §7 (API Endpoints — all queue/stream endpoints)
- §8.1, §8.3, §8.4 (Data Models)
- Lessons Learned: #1, #2, #3, #4, #5, #6, #10

---

## Sprint 5 — LLM Integration

**Goal:** Real AI responses via LM Studio or Ollama.

### Deliverables
- [ ] `services/llm_provider.py` — LM Studio + Ollama abstraction
- [ ] `services/prompt_assembler.py` — system + role + mode + context(survey) + history
- [ ] Admin LLM tab (provider health, model select, parameters)
- [ ] Streaming response from LLM through full pipeline
- [ ] Health check with try-except (lesson-learned #3)
- [ ] _dev_auto_process with error handling (lesson-learned #2)

### Acceptance Criteria
- [ ] Backend connects to LM Studio at configured endpoint
- [ ] Backend connects to Ollama at configured endpoint
- [ ] Admin LLM tab shows online/offline status for each provider
- [ ] Admin can select model, set temperature, num_ctx, max_tokens
- [ ] User message → real LLM response streams back to chat
- [ ] Prompt includes: system prompt + role prompt + survey context
- [ ] Conversation history maintained per session
- [ ] LLM failure → graceful error message to user (not crash)
- [ ] check_health() wrapped in try-except
- [ ] _dev_auto_process wrapped in try-except, pushes error to stream
- [ ] Mock LLM fallback works when no provider available

### Spec Sections Covered
- §4.2.3 (LLM Tab), §9.1 (Backend Config — LLM settings)
- Lessons Learned: #2, #3, #9

---

## Sprint 6 — Admin Panel (Complete)

**Goal:** All 6 admin tabs functional.

### Deliverables
- [ ] Prompts tab: two-column editor with categories
- [ ] RAG tab: upload docs, list, delete, reindex button
- [ ] Sessions tab: list with filters, view conversation, flag/unflag
- [ ] SMTP tab: config form, test connection button
- [ ] Admin tab navigation with blue underline active indicator
- [ ] Admin header: uni-dark background, logout button

### Acceptance Criteria
- [ ] Prompts tab shows all prompt files grouped by category
- [ ] Editing a prompt and saving persists to `/app/data/prompts/`
- [ ] Last modified timestamp shown per prompt
- [ ] RAG: upload .md/.txt/.json → file appears in list
- [ ] RAG: delete removes file, reindex rebuilds index
- [ ] Sessions: list shows all sessions with token, role, mode, dates
- [ ] Sessions: filter by All/Active/Completed/Flagged
- [ ] Sessions: click session → view conversation history
- [ ] Sessions: flag/unflag toggle
- [ ] SMTP: save config, test connection shows success/failure
- [ ] Tab navigation: active tab has blue underline
- [ ] Admin header matches uni-dark (#1a1a2e)
- [ ] Logout clears JWT and returns to login

### Spec Sections Covered
- §4.2 (Admin Tabs — all subsections)
- §5.4 (Component Style Reference — admin)
- §11 (Persistent Storage)

---

## Sprint 7 — RAG + MemGPT/Letta

**Goal:** AI uses uploaded documents for context. Long conversations compressed.

### Deliverables
- [ ] `services/rag_service.py` — LlamaIndex indexing + retrieval
- [ ] RAG integrated into prompt assembly
- [ ] Letta/MemGPT context compression for long conversations
- [ ] RAG config: chunk_size, similarity_top_k, embedding_model

### Acceptance Criteria
- [ ] Upload document via admin → appears in RAG index
- [ ] Ask question about uploaded document → AI references it
- [ ] RAG context injected into prompt (visible in debug logs)
- [ ] Reindex rebuilds the full index
- [ ] Long conversation (>10 exchanges) → Letta compresses context
- [ ] Compression threshold configurable via admin LLM tab
- [ ] AI responses remain coherent after compression

### Spec Sections Covered
- §4.2.4 (RAG Tab), §9.1 (Backend Config — RAG settings)

---

## Sprint 8 — Session Management & Finalization

**Goal:** Sessions persist to disk, recover across restarts, and generate summary + report on closure.

### Deliverables
- [ ] `services/session_store.py` — JSON file persistence per session directory
- [ ] Real-time conversation logging to `/app/data/sessions/{token}/conversation.jsonl`
- [ ] Session recovery endpoint on frontend sidecar
- [ ] "End Session" button in ChatShell (red border)
- [ ] Session closure flow (§3.6): summary → report → mark completed → SMTP alert
- [ ] Inactivity timeout auto-closure (configurable, e.g. 2h)
- [ ] Admin "Generate Report" / "Generate Summary" buttons per session
- [ ] Session state: active, completed, flagged

### Acceptance Criteria
- [ ] Session data persists to `/app/data/sessions/{token}/` directory
- [ ] `session.json` contains metadata (survey, language, role, timestamps, status)
- [ ] `conversation.jsonl` appended in real-time as messages flow
- [ ] Recover session by token → loads conversation, survey, language
- [ ] Resume window: 48h worker, 120h organizer
- [ ] Expired token → error message
- [ ] "End Session" button → summary streamed to chat → saved as `summary.md`
- [ ] "End Session" button → report generated in background → saved as `report.md`
- [ ] Report skipped for "training" mode sessions
- [ ] Session marked as "completed" in admin
- [ ] Admin can view completed session with conversation, summary, and report
- [ ] Admin can trigger report/summary generation on demand for any session
- [ ] Inactivity timeout closes session and generates report automatically
- [ ] Session data survives container restart (Docker volume)

### Spec Sections Covered
- §3.3 (Session Management), §3.5 (Chat — End Session), §3.6 (Session Closure)
- §4.2.5 (Sessions Tab — report generation), §8.1 (SubmitMessageRequest — finalize)
- §11 (Persistent Storage — session directory structure)

---

## Sprint 9 — SMTP Integration

**Goal:** Email auth codes, report forwarding, admin notifications.

### Deliverables
- [ ] `services/smtp_service.py` — send emails
- [ ] Auth code generation + verification for organizer flow
- [ ] Report forwarding (send completed reports via email)
- [ ] Admin notifications (flagged sessions, errors)
- [ ] SMTP tab: test connection

### Acceptance Criteria
- [ ] SMTP config saved and loaded from persistent storage
- [ ] Test connection → shows success/failure with error message
- [ ] Organizer auth: email sent with 6-digit code
- [ ] Code verification: valid code → proceed, invalid → error
- [ ] Code expiry: 10 minutes
- [ ] Completed session → report emailed to configured address
- [ ] Flagged session → notification emailed to admin
- [ ] Email send failure → logged, doesn't crash system

### Spec Sections Covered
- §4.2.6 (SMTP Tab), §3.1 (Auth phase)

---

## Sprint 10 — Polish, Testing, Production Deployment

**Goal:** Production-ready. Both machines. Everything works.

### Deliverables
- [ ] End-to-end testing on same machine
- [ ] Migrate frontend to Mac Mini
- [ ] End-to-end testing across machines
- [ ] Error handling audit (all try-except, all edge cases)
- [ ] Performance check (streaming latency, poll interval)
- [ ] Security audit (CORS, input validation, guardrails)
- [ ] Documentation update (all docs current)

### Acceptance Criteria
- [ ] Full flow works on Mac Studio (both containers): language → chat → summary
- [ ] Full flow works across machines (Mac Studio backend, Mac Mini frontend)
- [ ] Worker flow: no auth, basic survey, chat, summary
- [ ] Organizer flow: email auth, full survey, chat, full report
- [ ] Session recovery works across restart
- [ ] Admin panel fully functional (all 6 tabs)
- [ ] RAG retrieval works with real documents
- [ ] SMTP sends emails (auth codes + reports)
- [ ] No console errors in browser
- [ ] No unhandled exceptions in backend logs
- [ ] Docker containers restart cleanly (data persists)
- [ ] Response streaming is smooth (no batching)
- [ ] Poll interval ≤ 2s response time

### Spec Sections Covered
- All sections — full product verification

---

## Progress Tracking Rules

1. **Never mark a task `[x]` unless the acceptance criterion actually passes**
2. **If a criterion fails, document WHY in STATUS.md**
3. **If a criterion requires spec change, follow the DEVIATION PROTOCOL in CLAUDE.md**
4. **After each sprint, copy the acceptance results to STATUS.md**
5. **CHANGELOG.md gets a new entry for every sprint**
