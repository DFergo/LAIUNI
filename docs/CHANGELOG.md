# HRDD Helper — Changelog

## v2.0 — Clean Rewrite

### Sprint 7b — Context Compression (2026-03-10)
- `services/context_compressor.py`: Incremental compression with running summary per session
- `prompts/context_compression.md`: Dedicated compression prompt preserving names, dates, facts, case data
- Token estimation before every LLM call (logged: token count + message count)
- Two-phase compression: incremental summary updates + injection when inference hits threshold
- Configurable threshold via admin panel slider (50-90% of context window)
- Direct HTTP calls to summariser (avoids stream conflicts with inference)
- `<think>` block stripping for Qwen3 summariser responses
- Admin LLM tab redesigned:
  - Context Window field visible for all providers (not just Ollama)
  - Provider-specific hints (Ollama override vs LM Studio manual match)
  - Compression Threshold slider with calculated trigger point display
  - Removed summariser max_tokens from UI (internal detail)
- Fix: model selector auto-corrects when switching provider (was keeping old provider's model name)
- ADR-009: Documented decision to use simple compression over Letta (Sprint 12 for future swap)
- `/git` command: generates commit + push to GitHub and Gitea

### Sprint 7a — RAG with LlamaIndex (2026-03-10)
- `services/rag_service.py`: LlamaIndex vector index with sentence-transformers embeddings
- Embedding model: `all-MiniLM-L6-v2` (80MB, CPU-only, auto-downloaded from HuggingFace)
- Documents indexed from `/app/data/documents/`, index persisted to `/app/data/rag_index/`
- RAG chunks injected per-message as system context before the user's latest message
- Admin Reindex button now triggers real re-indexing (was stub)
- Index loads from disk on container restart — no re-embedding needed
- Lazy initialization: embedding model only loaded when first needed
- Dependencies: `llama-index-core`, `llama-index-readers-file`, `llama-index-embeddings-huggingface`, `sentence-transformers`

### Sprint 6b — Knowledge Base + Documentation (2026-03-10)
- Knowledge base: `glossary.json` (15 domain terms, 6 languages) + `organizations.json` (14 entries)
- Backend endpoints: `/admin/knowledge/glossary`, `/admin/knowledge/organizations` (GET/PUT)
- Prompt assembler: glossary + organizations injected as layer 5 in every session context
- Admin RAG tab: Glossary editor (add/edit/delete terms with translations) + Organizations Directory editor
- Default knowledge files installed on first startup, atomic writes
- Spec §13: Added guardrails (§13.1), session integrity (§13.2), internal UNI assessment (§13.3), phase-based prompt loading (§13.4)
- Milestones: Sprint 8 updated with internal assessment, new Sprint 10 for guardrails
- `docs/knowledge/prompt-assembly-flow.md`: Complete prompt architecture documentation
- `docs/INSTALL.md`: Installation and usage guide

### Sprint 6 — Admin Panel Complete (2026-03-10)
- **Prompts tab**: two-column editor with 5 categories (System, User, Use Cases, Context, Post-Processing), save with dirty tracking
- **RAG tab**: upload documents (.md/.txt/.json, 10MB limit), list with size/date, delete, reindex stub
- **Sessions tab**: list all sessions with All/Flagged filters, view conversation detail, flag/unflag toggle
- **SMTP tab**: full config form (host, port, username, password, from address, admin notify, TLS toggle), test connection stub
- Backend: 4 new router modules (`prompts.py`, `sessions.py`, `rag.py`, `smtp.py`) with 13 endpoints
- SMTP config persists to `/app/data/smtp_config.json` with atomic writes
- RAG documents stored in `/app/data/documents/` (indexing deferred to Sprint 7)
- Fix: survey `type` field now always sent from frontend (was conditional on role, causing "unknown" mode for worker/representative sessions)
- Fix: session mode default changed from "unknown" to "documentation"
- Added `python-multipart` dependency for file upload support

### Sprint 5b — LLM Tab Improvements (2026-03-09)
- Split LLM admin tab into Inference and Context Compression (Letta) subpanels
- Toggle to enable/disable Letta summariser
- Context window (num_ctx) field for Ollama on both panels
- Hints with recommended values and page equivalents for all parameters
- Fix: health refresh no longer overwrites unsaved settings edits
- Discard Changes and Reset to Defaults buttons

### Sprint 5 — LLM Integration (2026-03-09)
- `services/llm_provider.py`: LM Studio + Ollama via OpenAI-compatible API, streaming + non-streaming
- `services/prompt_assembler.py`: Modular prompt assembly (core + role + mode + survey context)
- `services/session_history.py`: In-memory conversation history per session token
- 11 default prompt files: core.md, worker.md, worker_representative.md, organizer.md, officer.md, documentation.md, advisory.md, training.md, context_template.md, session_summary.md, internal_case_file.md
- Auto-install defaults to `/app/data/prompts/` on first startup (won't overwrite edits)
- `api/v1/admin/llm.py`: Health check, model listing, settings CRUD
- Admin LLM tab: provider status (green/red), model dropdowns, temperature slider, max_tokens, num_ctx
- LLM settings persist to `/app/data/llm_settings.json`
- `<think>` block filtering: Qwen3 reasoning tokens stripped from user-visible response
- Mock LLM fallback when no provider is available
- Health checks wrapped in try-except (lesson #3)
- All background processing wrapped in try-except with error push to stream (lesson #2)

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
