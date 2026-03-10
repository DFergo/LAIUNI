# HRDD Helper — Claude Code Project Instructions

## Project Identity

**Name:** HRDD Helper
**Owner:** Daniel Fernandez (UNI Global Union / Malicia Fernandez)
**Repo:** https://github.com/DFergo/LAIUNI (public)
**Purpose:** Self-hosted AI assistant for documenting labor rights violations against international frameworks

## Communication Style

- Respond in the language Daniel uses (ES/EN/FR)
- Be direct, pragmatic, European-style professional tone
- Daniel is NOT a programmer — he develops with AI assistance
- Flag risks and problems proactively
- Don't over-explain basics — Daniel learns fast

## Architecture Overview

Pull-inverse / air-gap architecture with 2 containers:

- **Backend** (`docker-compose.backend.yml`, port 8000): All logic — LLM, RAG, MemGPT/Letta, admin panel, polling, SMTP. Landing page = admin login.
- **Frontend** (`docker-compose.frontworker.yml` port 8091, `docker-compose.frontorganizer.yml` port 8090): User-facing React SPA + FastAPI sidecar message queue. No admin. Two profiles from one image.

**Key principle:** Frontend is passive. Backend initiates ALL communication by polling. Frontend never knows where backend is.

## Tech Stack

### Frontend
- React 18 + TypeScript
- Vite 6
- Tailwind CSS 3.4
- react-markdown
- EventSource API (SSE streaming)
- Nginx (reverse proxy + SPA routing)

### Backend
- FastAPI (Python, async)
- Pydantic (validation)
- httpx (async HTTP)
- sse-starlette (SSE)
- LM Studio / Ollama (LLM)
- LlamaIndex + sentence-transformers (RAG)
- Letta (context compression / MemGPT)
- bcrypt + JWT (admin auth)
- JSON file storage (no database)

### Infrastructure
- Docker + Docker Compose
- Nginx (frontend container)

## Production Environment

| Machine | IP | Role | Ports |
|---------|-----|------|-------|
| Mac Studio M3 Ultra | 10.210.66.103 | Backend + LLM | 8000, 1234 (LM Studio), 11434 (Ollama) |
| Mac Mini M4 | 10.210.66.130 | Frontend Worker + Organizer | 8091, 8090 |

**Dev/Test:** Both containers on same machine (Mac Studio). Use host IP for inter-container communication, NOT Docker internal networking.

## Visual Design — PRESERVE THESE

```
UNI Blue:  #003087  (headers, buttons, links, user chat bubbles)
UNI Red:   #E31837  (alerts, errors, destructive actions)
UNI Dark:  #1a1a2e  (admin panel header)
Background: gray-50
Cards: white, rounded-xl, shadow-md, border-gray-200
```

The UI is clean and minimal. Keep it that way. See `docs/SPEC-v2.md` section 5 for full style reference.

## Project Structure

```
/
├── CLAUDE.md                          ← You are here
├── docs/
│   ├── SPEC-v2.md                     ← Full product specification
│   ├── MILESTONES.md                  ← Sprint milestones + acceptance criteria
│   ├── STATUS.md                      ← Current sprint status
│   ├── CHANGELOG.md                   ← Sprint-by-sprint changes
│   ├── architecture/
│   │   ├── message-flow.md            ← Detailed message flow documentation
│   │   └── decisions.md               ← Architecture Decision Records
│   └── knowledge/
│       ├── frameworks.md              ← ILO, OECD, UNGP, EU CSDDD, FSC reference
│       ├── polling-architecture.md    ← Pull-inverse deep dive
│       └── lessons-learned.md         ← Bugs, fixes, pitfalls from v1
├── config/
│   ├── deployment_backend.json
│   ├── deployment_frontend_worker.json
│   ├── deployment_frontend_organizer.json
│   └── nginx/
│       └── frontend.conf
├── src/
│   ├── backend/                       ← Python FastAPI backend
│   └── frontend/                      ← React + TypeScript frontend
├── docker-compose.backend.yml
├── docker-compose.frontworker.yml
├── docker-compose.frontorganizer.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── .claude/
    ├── settings.json
    └── commands/
        ├── spec.md                    ← /spec command
        ├── status.md                  ← /status command
        ├── sprint.md                  ← /sprint command
        └── deploy.md                  ← /deploy command
```

## Key Documents — READ ORDER

Before starting ANY sprint, read these in order:

1. **`docs/MILESTONES.md`** — Sprint milestones with acceptance criteria. Source of truth for what to build and when it's done.
2. **`docs/SPEC-v2.md`** — Complete product specification. Every feature must match this.
3. **`docs/STATUS.md`** — Current sprint status, what works, what's broken.
4. **`docs/knowledge/lessons-learned.md`** — Critical bugs and pitfalls from v1. READ before touching polling, SSE, or registry code.
5. **`docs/architecture/message-flow.md`** — Detailed message flow with sequence diagrams.
6. **`docs/architecture/decisions.md`** — Architecture Decision Records. Understand WHY before changing HOW.

## Development Rules

### Git
- **NEVER touch git configuration** (remotes, user, etc.). Only provide commands for Daniel to execute.
- Two remotes: `origin` (GitHub) and `gitea` (http://100.77.80.55:3000/Daniel/LAIUNI). Always push to both.
- Push command: `git push origin main && git push gitea main`
- Use `/git` command to generate commit + push commands.

### Docker
- Always use separate compose files (never merge backend + frontend)
- Dev mode: `HRDD_DEV_MODE=true` on backend enables local processing with mock LLM
- Frontend containers do NOT have DEV_MODE
- After code changes: `docker builder prune -f && docker compose -f <file> build --no-cache && docker compose -f <file> up -d`

### Testing
- Both containers must communicate via host IP (not Docker internal network)
- Register frontend in backend admin by URL (e.g., `http://10.210.66.103:8091` for same-machine dev)
- Test the full flow: language → disclaimer → session → survey → chat → response

### Code Style
- Frontend: TypeScript strict, functional React components, Tailwind utility classes
- Backend: Python 3.11+, async/await, Pydantic models, type hints everywhere
- No class-based React components
- No CSS files — Tailwind only
- No React Router — hash-based routing

## MANDATORY GUARDRAILS — Read Before Every Action

These are non-negotiable checkpoints. Follow them on EVERY code change, no exceptions.

### PRE-FLIGHT CHECK (Before writing ANY code)

Before implementing anything, ALWAYS:

1. **Read `docs/SPEC-v2.md`** — Verify the feature you're about to build matches the spec exactly
2. **Read `docs/knowledge/lessons-learned.md`** — Check if any v1 pitfall applies to what you're doing
3. **Read `docs/STATUS.md`** — Confirm you're working on the current sprint, not jumping ahead
4. **Verify architecture compliance:**
   - Does this change respect pull-inverse? (frontend passive, backend initiates)
   - Does this change keep the two containers independent?
   - Does persistent data go to `/app/data` (Docker volume)?
   - Does the UI use ONLY Tailwind classes and the UNI color palette?

If ANY answer is "no" or "unclear" → STOP and ask Daniel before proceeding.

### MID-FLIGHT CHECK (During implementation)

After every significant piece of code (new component, new endpoint, new service):

1. **Spec alignment:** Does this match SPEC-v2.md section by section? Quote the spec section.
2. **No scope creep:** Am I adding anything NOT in the spec? If yes → stop, flag it.
3. **Pitfall scan:** Cross-check against `lessons-learned.md` — am I repeating a v1 mistake?
4. **Update `docs/STATUS.md`:** Mark the specific sub-task as done with `[x]`

### POST-FLIGHT CHECK (After completing a sprint)

Before presenting work to Daniel:

1. **Full spec diff:** Compare every deliverable against SPEC-v2.md requirements for this sprint
2. **Regression list:** Explicitly state what could break from this change
3. **Update `docs/STATUS.md`:** Sprint marked complete, next sprint outlined
4. **Update `docs/CHANGELOG.md`:** Add sprint entry with what changed
5. **Provide git commit command** (heredoc format, never execute directly)
6. **Provide docker rebuild commands** for affected containers
7. **Provide test checklist** specific to what was built

### DEVIATION PROTOCOL

If you need to deviate from the spec (better approach found, spec has a gap, etc.):

1. **STOP implementation**
2. **Document the deviation** — what the spec says vs. what you propose
3. **Explain why** — concrete technical reason
4. **Ask Daniel** — never deviate silently
5. If approved, **update SPEC-v2.md** before continuing

## Sprint Workflow

1. Read current `docs/STATUS.md`
2. Run PRE-FLIGHT CHECK (above)
3. Plan sprint changes
4. Implement in small, testable increments (MID-FLIGHT CHECK after each)
5. Run POST-FLIGHT CHECK
6. Update `docs/STATUS.md` after each sprint
7. Update `docs/CHANGELOG.md` with what changed
8. Provide git commit command (never execute git directly)
9. Provide docker rebuild commands

## Message Flow (Quick Reference)

```
User types → POST /internal/queue → Nginx → Sidecar (enqueue)
                                                    ↑
React EventSource ← GET /internal/stream/{token} ←──┘
                                                    ↓
Backend polls → GET {frontend_url}/internal/queue (dequeue)
Backend → LLM inference
Backend → POST {frontend_url}/internal/stream/{token}/chunk
Sidecar → SSE event → React (real-time tokens)
```

## Common Pitfalls (from v1)

1. **EventSource onerror must unblock UI** — track failures, call `onError()` after 3 attempts
2. **`_dev_auto_process` needs try-except** — wrap in error handler, push error to stream
3. **`check_health()` can throw** — always wrap in try-except
4. **Nginx must disable buffering for SSE** — `proxy_buffering off; proxy_cache off;`
5. **Frontend registry persistence** — save to JSON after every mutation, not just on shutdown
6. **Docker volumes for persistence** — `/app/data` must be a named volume
7. **Same React app in both images** — both Dockerfiles build from `src/frontend/`. Backend serves admin-only at root.
