# HRDD Helper v2 — Product Specification

**Version:** 2.0
**Date:** 2026-03-09
**Author:** Daniel Fernandez / Malicia Fernandez
**Organization:** UNI Global Union — Graphical & Packaging Sector

---

## 1. Overview

HRDD Helper is a self-hosted AI assistant that guides workers, union representatives, organizers, and officers through structured consultations to document labor rights violations against international frameworks (ILO Conventions, OECD Guidelines, UN Guiding Principles, EU CSDDD, FSC Standards).

The system uses a **pull-inverse / air-gap architecture**: the frontend is a passive server that holds user messages. The backend initiates ALL communication by polling the frontend. The frontend never knows where the backend is.

---

## 2. Architecture

### 2.1 Containers

Two independent containers, each with its own Docker Compose file:

| Container | Compose File | Port | Description |
|-----------|-------------|------|-------------|
| **Backend** | `docker-compose.backend.yml` | 8000 | All logic: LLM, RAG, MemGPT, admin panel, polling, SMTP |
| **Frontend** | `docker-compose.frontworker.yml` / `docker-compose.frontorganizer.yml` | 8091 (worker) / 8090 (organizer) | User-facing UI + message queue sidecar |

Both containers can run on the same machine or on separate machines. Communication is always via HTTP over the network (never Docker internal networking).

### 2.2 Frontend Container

```
┌──────────────────────────────────────────────────┐
│              FRONTEND CONTAINER                   │
├─────────────────────┬────────────────────────────┤
│  Nginx (Port 80)    │  FastAPI Sidecar (Port 8000)│
├─────────────────────┼────────────────────────────┤
│ • React SPA         │ • POST /internal/queue      │
│ • Static assets     │ • GET  /internal/queue      │
│ • SPA fallback      │ • GET  /internal/stream/{t} │
│ • Proxy /internal/* │ • GET  /internal/config     │
│                     │ • GET  /internal/session/... │
│                     │ • POST /internal/auth/...    │
│                     │ • In-memory message queue    │
└─────────────────────┴────────────────────────────┘
```

- **Nginx** serves the React SPA and proxies `/internal/*` to the FastAPI sidecar
- **FastAPI sidecar** holds the message queue and serves config
- **No admin menu** on frontend
- **Two profiles** in one container image, selected via compose file:
  - `frontworker`: port 8091, `auth_required: false`
  - `frontorganizer`: port 8090, `auth_required: true`

### 2.3 Backend Container

```
┌──────────────────────────────────────────────────┐
│              BACKEND CONTAINER                    │
├──────────────────────────────────────────────────┤
│  FastAPI (Port 8000)                              │
├──────────────────────────────────────────────────┤
│ • Admin Panel (React SPA at /)                    │
│ • Polling Service (background task)               │
│ • Frontend Registry                               │
│ • Session Store                                   │
│ • RAG Service (LlamaIndex)                        │
│ • LLM Provider (LM Studio / Ollama)               │
│ • MemGPT / Letta (context compression)            │
│ • Prompt Assembler                                │
│ • SMTP Service                                    │
│ • Message Queue (for response streaming)          │
└──────────────────────────────────────────────────┘
        ↓ HTTP
┌──────────────────────────────────────────────────┐
│  External Services                                │
│ • LM Studio (port 1234)                           │
│ • Ollama (port 11434)                             │
└──────────────────────────────────────────────────┘
```

- **Landing page** is the admin login screen
- **First run:** prompts to create admin username and password
- **Remember password** option (JWT with configurable expiry)
- Backend serves its own React admin app (no frontend dependency)

### 2.4 Message Flow

```
1. User types message in React UI
2. React → POST /internal/queue → Nginx → FastAPI sidecar (enqueue)
3. React opens EventSource → GET /internal/stream/{session_token}
4. Backend polling loop → GET {frontend_url}/internal/queue (dequeue)
5. Backend → LLM inference (with system prompt + RAG context + conversation history)
6. Backend → POST {frontend_url}/internal/stream/{token}/chunk (push tokens)
7. FastAPI sidecar → SSE event → React (real-time token display)
8. On completion: event "done" with full response text
```

### 2.5 Nginx Configuration (Frontend)

```nginx
server {
    listen 80;

    # React SPA
    location / {
        root /app/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Static assets (1 year cache, fingerprinted by Vite)
    location /assets/ {
        root /app/frontend/dist;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Health check
    location /nginx-health {
        return 200 'ok';
    }

    # API proxy to FastAPI sidecar — SSE streaming enabled
    location /internal/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_read_timeout 600s;
    }
}
```

---

## 3. Frontend — User Flow

### 3.1 Phase State Machine

```
loading → language → disclaimer → session → auth? → survey → chat
```

| Phase | Component | Description |
|-------|-----------|-------------|
| `loading` | — | Fetches deployment config from sidecar |
| `language` | `LanguageSelector` | Grid of 16 language buttons |
| `disclaimer` | `DisclaimerPage` | Purpose statement + accept button |
| `session` | `SessionPage` | New session or recover existing |
| `auth` | `AuthPage` | Email verification (organizer only) |
| `survey` | `SurveyPage` | Context collection form |
| `chat` | `ChatShell` | Real-time streaming chat |

### 3.2 Supported Languages (16)

English, Spanish, French, German, Portuguese, Arabic, Chinese, Hindi, Indonesian, Japanese, Korean, Russian, Turkish, Vietnamese, Thai, Swahili

### 3.3 Session Management

- **Token format:** `WORD-NUMBER` (e.g., `ALPINE-4523`)
- **Word pool:** 24 mountain/nature words
- **Number:** 4-digit random
- **Resume window:** 48h (worker), 120h (organizer) — configurable
- **Recovery:** User enters token → `GET /internal/session/{token}/recover` → restores conversation, survey, language

### 3.4 Survey Fields

| Field | Worker | Representative | Organizer | Officer |
|-------|--------|---------------|-----------|---------|
| Role select | ✓ | ✓ | ✓ | ✓ |
| Mode select | — | — | ✓ | ✓ |
| Name | — | — | ✓ | ✓ |
| Position | — | — | ✓ | ✓ |
| Union | — | — | ✓ | ✓ |
| Email | — | — | ✓ | ✓ |
| Company | ✓ | ✓ | ✓ | — |
| Country/Region | ✓ | ✓ | ✓ | — |
| Situation description | ✓ | ✓ | ✓ | ✓ |

**Consultation modes** (organizer/officer only): Documentation, Advisory, Training

### 3.5 Chat Interface

- **User messages:** right-aligned, `uni-blue` background, white text
- **Assistant messages:** left-aligned, white background, rendered as Markdown
- **Streaming indicator:** pulsing blue dot with "Preparing..." text
- **Input:** textarea (2 rows), Enter to send, Shift+Enter for newline
- **Send button:** blue, disabled while streaming
- **"End Session" button:** red border, triggers session closure flow (§3.6)
- **SSE streaming:** EventSource API, events: `token`, `done`, `error`, `queue_position`

### 3.6 Session Closure & Report Generation

#### Trigger mechanisms (in priority order)

1. **User clicks "End Session"** — primary path. The AI should suggest using this button when it determines it has sufficient information to generate a useful report.
2. **Inactivity timeout** — if a session has no activity for a configurable period (e.g., 2 hours), the backend auto-closes it and generates the report. The user is no longer present, but the report is still created.
3. **Admin manual trigger** — Sessions tab in admin panel shows whether summary/report were generated. Admin can trigger generation on demand for any session, regardless of status.

#### Closure flow (sequential)

```
1. "End Session" triggered (button, timeout, or admin)
2. Backend loads full conversation from /app/data/sessions/{token}/conversation.jsonl
3. Step A — Summary (visible to user if still connected):
   - Load session_summary.md prompt
   - Send full conversation + prompt to inference LLM
   - Response streamed to chat as final assistant message
   - Save as /app/data/sessions/{token}/summary.md
4. Step B — Internal report (background, user does NOT see this):
   - Load internal_case_file.md prompt
   - Send full conversation + prompt to inference LLM
   - Save as /app/data/sessions/{token}/report.md
   - NOTE: Skipped for "training" mode sessions
5. Mark session status as "completed"
6. SMTP notifications:
   - Alert admin that session was completed
   - Optionally send report to registered users (configurable)
```

#### Important notes

- Both summary and report use the **inference LLM** (main model), NOT the summariser/Letta model. These are document generation tasks, not context compression.
- The `session_summary.md` prompt produces a user-facing summary in the chat language.
- The `internal_case_file.md` prompt produces an internal report (may be 20+ pages). Written in the admin's configured language.
- Reports are saved as Markdown files — future: downloadable from admin, optionally sent via SMTP.
- If the user disconnects before "End Session", the inactivity timeout ensures reports are still generated.

---

## 4. Backend — Admin Panel

### 4.1 Authentication

- **First run:** "Create Admin Account" form (password + confirm, min 8 chars)
- **Subsequent:** password login with "Remember me" option
- **Storage:** bcrypt hash at `/app/data/.admin_hash`, JWT secret at `/app/data/.jwt_secret`
- **JWT expiry:** 24h (default), extended with "remember me"
- **Landing page:** always the login screen (no user-facing content on backend)

### 4.2 Admin Tabs

#### 4.2.1 Frontends Tab

Register and monitor frontend instances.

- List of registered frontends: URL, type (worker/organizer), status, last seen
- **Add Frontend:** URL input → auto-discovery via `GET {url}/internal/config`
- Status indicators: online (green) / offline (red) / unknown (gray)
- Enable/disable polling per frontend
- Edit display name (cosmetic)

#### 4.2.2 Prompts Tab

Modular prompt editor with categories:

| Category | Files | Description |
|----------|-------|-------------|
| **System Prompt** | `core.md` | Base system instructions for the AI |
| **User Prompts** | `worker.md`, `worker_representative.md`, `organizer.md`, `officer.md` | Role-specific instructions |
| **Use Cases** | `documentation.md`, `advisory.md`, `training.md` | Mode-specific context |
| **Context Template** | `context_template.md` | Template for injecting survey data into prompt |
| **Post-Processing** | `session_summary.md`, `internal_case_file.md` | Summary and report generation prompts |

Layout: two-column (list left, editor right). Groups are expandable. Save button with last-modified timestamp.

#### 4.2.3 LLM Tab

- **Provider health status:** LM Studio / Ollama (online/offline indicators, auto-refresh)
- **Refresh** button (pulls model list and health from providers)
- **Inference panel:** provider select, model select, `temperature`, `max_tokens`, `num_ctx` (Ollama only). Hint text on each parameter with recommended values.
- **Context Compression (Letta) panel:** toggle enabled/disabled. When enabled: provider select, model select, `temperature`, `max_tokens`, `num_ctx` (Ollama only). Uses a separate, typically smaller model (e.g., 7B) to compress conversation context for the inference model. NOT used for session summaries or reports.
- **Buttons:** Save Settings, Discard Changes, Reset to Defaults
- Settings persist to `/app/data/llm_settings.json`
- Health refresh does NOT overwrite unsaved edits

#### 4.2.4 RAG Documents Tab

- Upload knowledge documents (`.md`, `.txt`, `.json`)
- List of indexed documents with size and date
- **Reindex** button (rebuilds LlamaIndex index)
- Delete individual documents
- Configuration: `chunk_size`, `similarity_top_k`, `embedding_model`

#### 4.2.5 Sessions Tab

- List of all sessions with filters: All, Active, Completed, Flagged
- Session details: token, role, mode, start time, last activity, message count
- View conversation history
- Flag/unflag sessions
- **Report status indicators:** shows whether summary and/or report were generated (checkmark/missing)
- **"Generate Report" button:** triggers report generation on demand for any session (useful for abandoned sessions or re-generation with updated prompts)
- **"Generate Summary" button:** same, for session summary
- Export session data

#### 4.2.6 SMTP Tab

- SMTP server configuration: host, port, username, password, TLS/SSL
- **Uses:**
  - Authentication codes (organizer email verification)
  - Report forwarding (send completed reports via email)
  - Admin notifications (alerts for flagged sessions, errors)
- Test connection button
- From address configuration

---

## 5. Visual Design

### 5.1 Color Palette

```
UNI Blue (Primary):  #003087  — Headers, buttons, links, user message bubbles
UNI Red (Secondary): #E31837  — Alerts, errors, destructive actions
UNI Dark:            #1a1a2e  — Admin panel header
Background:          gray-50  — Page background
Cards:               white    — Content cards with subtle borders
Text:                gray-700/800 — Body text
Secondary text:      gray-400 — Footer, labels
```

### 5.2 Tailwind Config

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        'uni-blue': '#003087',
        'uni-red': '#E31837',
        'uni-dark': '#1a1a2e',
      },
    },
  },
}
```

### 5.3 Layout

- **Framework:** Tailwind CSS 3.4 (utility-first)
- **Font:** System default (no custom fonts)
- **Rounded corners:** `rounded-lg`, `rounded-xl`
- **Shadows:** `shadow-md`, `shadow-lg`
- **Focus states:** `focus:ring-2 focus:ring-uni-blue`
- **Transitions:** `transition-colors` on interactive elements
- **Max width:** `max-w-4xl` centered for user flow, full width for admin

### 5.4 Component Style Reference

**Header:**
```
bg-uni-blue text-white px-6 py-4 shadow-md
Title: text-xl font-semibold "HRDD Helper"
Right: text-sm opacity-75 "UNI Global Union"
```

**Admin header:**
```
bg-uni-dark text-white
Title: "HRDD Helper — Admin Panel"
Logout button right-aligned
Tab bar with blue underline on active tab
```

**Buttons:**
```
Primary:     bg-uni-blue text-white rounded-lg px-4 py-2.5
Destructive: border border-uni-red text-uni-red rounded-lg
Disabled:    opacity-50 cursor-not-allowed
```

**Cards:**
```
bg-white rounded-xl shadow-md border border-gray-200 p-6
```

**Chat bubbles:**
```
User:      bg-uni-blue text-white rounded-lg — right aligned
Assistant: bg-white border rounded-lg — left aligned, prose markdown
```

**Footer:**
```
text-center text-xs text-gray-400 py-3
"This tool provides information, not legal advice. AI responses may contain errors."
Hidden during chat phase.
```

---

## 6. Tech Stack

### 6.1 Frontend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | React + TypeScript | 18.3.1 |
| Build | Vite | 6.0.5 |
| Styling | Tailwind CSS | 3.4 |
| Markdown | react-markdown | — |
| Streaming | EventSource API (native) | — |
| Web server | Nginx | latest |

### 6.2 Backend

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI (Python, async) |
| Config | Pydantic |
| HTTP client | httpx (async) |
| SSE | sse-starlette |
| LLM | LM Studio (OpenAI-compatible) / Ollama |
| RAG | LlamaIndex + sentence-transformers |
| Memory | Letta (context compression) |
| Auth | bcrypt + JWT |
| Storage | JSON files (filesystem) |

### 6.3 Infrastructure

| Component | Technology |
|-----------|-----------|
| Containers | Docker + Docker Compose |
| Orchestration | Manual / Portainer |
| Source control | Git (GitHub + Gitea) |

---

## 7. API Endpoints

### 7.1 Frontend Sidecar (exposed to React app and backend polling)

| Method | Endpoint | Description | Used by |
|--------|----------|-------------|---------|
| `GET` | `/internal/config` | Deployment config (type, auth, resume window) | React app, Backend discovery |
| `POST` | `/internal/queue` | Submit user message | React app |
| `GET` | `/internal/queue` | Poll pending messages | Backend polling |
| `GET` | `/internal/stream/{session_token}` | SSE stream of response tokens | React app |
| `POST` | `/internal/stream/{session_token}/chunk` | Push response chunk | Backend |
| `GET` | `/internal/session/{token}/recover` | Recover session data | React app |
| `POST` | `/internal/auth/email-verify` | Email verification | React app |

### 7.2 Backend (admin API)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin/status` | Check if admin account exists |
| `POST` | `/admin/setup` | Create admin account (first run) |
| `POST` | `/admin/login` | Admin login → JWT token |
| `GET` | `/admin/frontends` | List registered frontends |
| `POST` | `/admin/frontends` | Register frontend |
| `DELETE` | `/admin/frontends/{id}` | Remove frontend |
| `GET/PUT` | `/admin/prompts/*` | Prompt CRUD |
| `GET/PUT` | `/admin/llm/*` | LLM config |
| `GET/POST/DELETE` | `/admin/rag/*` | RAG document management |
| `POST` | `/admin/rag/reindex` | Rebuild RAG index |
| `GET` | `/admin/sessions` | List sessions |
| `GET` | `/admin/sessions/{token}` | Session detail |
| `GET/PUT` | `/admin/smtp` | SMTP config |
| `POST` | `/admin/smtp/test` | Test SMTP connection |

---

## 8. Data Models

### 8.1 SubmitMessageRequest

```typescript
{
  session_token: string       // e.g. "ALPINE-4523"
  content: string             // User message text
  message_id: string          // UUID
  timestamp: string           // ISO 8601
  language?: string           // e.g. "en", "es"
  survey?: SurveyData         // First message only
  finalize?: boolean          // Triggers summary + report generation
}
```

### 8.2 SurveyData

```typescript
{
  role: string                // "worker" | "representative" | "organizer" | "officer"
  type: string                // "documentation" | "advisory" | "training"
  name?: string
  position?: string
  union?: string
  email?: string
  company?: string
  countryRegion?: string
  description?: string
}
```

### 8.3 QueuedMessage (internal)

```python
{
  message_id: str
  session_token: str
  content: str
  timestamp: str
  language: str = "en"
  survey: dict | None
  finalize: bool = False
  created_at: float           # TTL tracking (300s expiry)
}
```

### 8.4 RegisteredFrontend

```python
{
  id: str                     # Auto-generated 8-char hex
  url: str                    # e.g. "http://10.210.66.130:8091"
  frontend_type: str          # "worker" | "organizer"
  name: str                   # Display name
  enabled: bool               # Polling active?
  status: str                 # "online" | "offline" | "unknown" (runtime)
  last_seen: str | None       # ISO timestamp
  created_at: str             # ISO timestamp
}
```

### 8.5 FrontendDeploymentConfig (sidecar response)

```python
{
  role: "frontend"
  frontend_type: str          # "worker" | "organizer"
  session_resume_window_hours: int
  disclaimer_enabled: bool
  auth_required: bool
}
```

---

## 9. Deployment Configuration

### 9.1 Backend Config (`deployment_backend.json`)

```json
{
  "role": "backend",
  "lm_studio_endpoint": "http://host.docker.internal:1234/v1",
  "lm_studio_model": "qwen3-235b-a22b",
  "ollama_endpoint": "http://host.docker.internal:11434",
  "ollama_summariser_model": "qwen2.5:7b",
  "ollama_num_ctx": 8192,
  "letta_compression_threshold": 0.80,
  "rag_documents_path": "./documents",
  "rag_index_path": "./data/rag_index",
  "rag_chunk_size": 512,
  "rag_similarity_top_k": 5,
  "streaming_enabled": true,
  "stream_chunk_size": 1,
  "poll_interval_seconds": 2
}
```

### 9.2 Frontend Worker Config (`deployment_frontend_worker.json`)

```json
{
  "role": "frontend",
  "frontend_type": "worker",
  "session_resume_window_hours": 48,
  "auth_required": false,
  "disclaimer_enabled": true,
  "output_worker_summary": true,
  "output_full_report": false
}
```

### 9.3 Frontend Organizer Config (`deployment_frontend_organizer.json`)

```json
{
  "role": "frontend",
  "frontend_type": "organizer",
  "session_resume_window_hours": 120,
  "auth_required": true,
  "disclaimer_enabled": true,
  "output_worker_summary": false,
  "output_full_report": true
}
```

---

## 10. Docker Compose Files

### 10.1 `docker-compose.backend.yml`

```yaml
services:
  hrdd-backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    volumes:
      - hrdd-data:/app/data
    environment:
      - DEPLOYMENT_JSON_PATH=/app/config/deployment_backend.json

volumes:
  hrdd-data:
```

### 10.2 `docker-compose.frontworker.yml`

```yaml
services:
  hrdd-frontend-worker:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "8091:80"
    volumes:
      - hrdd-fw-data:/app/data
    environment:
      - DEPLOYMENT_JSON_PATH=/app/config/deployment_frontend_worker.json

volumes:
  hrdd-fw-data:
```

### 10.3 `docker-compose.frontorganizer.yml`

```yaml
services:
  hrdd-frontend-organizer:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "8090:80"
    volumes:
      - hrdd-fo-data:/app/data
    environment:
      - DEPLOYMENT_JSON_PATH=/app/config/deployment_frontend_organizer.json

volumes:
  hrdd-fo-data:
```

---

## 11. Persistent Storage

All persistent data lives in Docker volumes mapped to `/app/data`:

### Backend volume (`hrdd-data`)

```
/app/data/
├── .admin_hash              # bcrypt admin password
├── .jwt_secret              # JWT signing key
├── frontends.json           # Registered frontends
├── llm_settings.json        # LLM configuration (inference + summariser)
├── sessions/                # Session data (one directory per session)
│   └── {token}/
│       ├── session.json         # Metadata: survey, language, role, timestamps, status
│       ├── conversation.jsonl   # Messages appended in real-time (one JSON per line)
│       ├── summary.md           # Generated at session closure (user-facing)
│       └── report.md            # Generated at session closure (internal, skipped for training)
├── rag_index/               # LlamaIndex vector index
├── documents/               # RAG source documents
└── prompts/                 # Editable prompt files
    ├── core.md
    ├── worker.md
    ├── worker_representative.md
    ├── organizer.md
    ├── officer.md
    ├── documentation.md
    ├── advisory.md
    ├── training.md
    ├── context_template.md
    ├── session_summary.md
    └── internal_case_file.md
```

### Frontend volume (`hrdd-fw-data` / `hrdd-fo-data`)

```
/app/data/
└── (message queue state if needed for persistence)
```

---

## 12. Production Environment

| Machine | IP | Role | Ports |
|---------|-----|------|-------|
| Mac Studio M3 Ultra | `10.210.66.103` | Backend + LLM inference | 8000, 1234 (LM Studio), 11434 (Ollama) |
| Mac Mini M4 | `10.210.66.130` | Frontend Worker + Frontend Organizer | 8091 (worker), 8090 (organizer) |

### Dev/Test Mode

Both containers on the same machine. Backend has `HRDD_DEV_MODE=true` which enables `_dev_auto_process` — processes messages locally without HTTP polling (uses mock LLM if no provider available).

---

## 13. Security Considerations

- Frontend never knows backend location (pull-inverse / air gap)
- Admin panel protected by bcrypt password + JWT
- Email verification for organizer mode
- Session tokens are non-sequential (word + random number)
- No sensitive data in URL query parameters
- RAG documents stored server-side only
- CORS configured per deployment
- Input validation via Pydantic
- Guardrails: injection detection, rate limiting (configurable)
- File upload: size limits (25MB default), type restrictions

---

## 14. Key Design Decisions

1. **Pull-inverse architecture:** Backend initiates all connections. Frontend is passive. This allows deploying frontends in restricted networks where outbound connections are blocked.

2. **Single image, two profiles:** Frontend worker and organizer share the same Docker image. The profile (auth required, report type, session window) is set by the deployment config JSON.

3. **Backend serves admin only:** No user flow on backend. Landing page is admin login. This eliminates confusion between backend and frontend roles.

4. **Modular prompts:** System prompt, role prompts, mode prompts, and context template are separate files. Admin can edit each independently without touching code.

5. **JSON file storage:** No database dependency. Sessions, config, and registry are JSON files in Docker volumes. Simple, portable, no setup required.

6. **SSE over WebSocket:** Server-Sent Events for streaming. Simpler than WebSocket, works through proxies and load balancers, unidirectional (server→client) which matches the use case.

---

## 15. Known Limitations / Technical Debt

- No database (JSON files only) — acceptable for current scale
- No horizontal scaling (single backend polls all frontends)
- No end-to-end encryption between frontend and backend
- Admin panel served as separate React build from same codebase
- No automated backups of session data
- No multi-admin support (single admin account)
