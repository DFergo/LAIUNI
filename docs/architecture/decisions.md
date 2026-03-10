# Architecture Decision Records

## ADR-001: Pull-Inverse / Air-Gap Architecture

**Decision:** Backend initiates all communication by polling frontends. Frontends are passive.

**Context:** HRDD Helper may be deployed in union offices with restricted networks. Workers documenting violations need privacy. The frontend should not make outbound connections to unknown servers.

**Consequences:**
- Frontend can run in networks with no outbound access
- Backend must know frontend URLs (registered via admin panel)
- Latency = poll interval (2s default) + processing time
- Message queue needed on frontend to hold messages between polls

## ADR-002: JSON File Storage (No Database)

**Decision:** All persistent data stored as JSON files in Docker volumes.

**Context:** System must be simple to deploy and maintain by non-technical staff. No database installation, backup procedures, or migration scripts.

**Consequences:**
- Simple deployment (just Docker)
- No query language needed
- Limited scalability (acceptable for current use)
- Must handle concurrent access carefully (atomic writes)
- Backups = copy the Docker volume

## ADR-003: Single Image, Two Profiles (Frontend)

**Decision:** One Dockerfile.frontend builds one image. Worker vs organizer is configured via deployment JSON.

**Context:** Worker and organizer flows are 95% identical. Only auth requirement, report type, and session window differ.

**Consequences:**
- Single image to maintain
- Profile selected by environment variable at runtime
- Different compose files for different ports and configs
- Same codebase serves both profiles

## ADR-004: Backend Serves Admin Only

**Decision:** Backend container serves only the admin panel at `/`. No user flow.

**Context:** In v1, both containers served the same React app. Opening the backend URL showed the user flow, causing confusion.

**Consequences:**
- Clear separation of concerns
- Backend build only includes admin components
- No accidental user access to backend
- Admin is always at the backend URL root, no `/#/admin` needed

## ADR-005: SSE Over WebSocket

**Decision:** Use Server-Sent Events for streaming, not WebSocket.

**Context:** Response streaming is unidirectional (server→client). SSE is simpler, works through HTTP proxies and load balancers, and has native browser support via EventSource API.

**Consequences:**
- Simpler implementation
- Works through Nginx without special config (just disable buffering)
- No bidirectional channel (not needed — user messages go via POST)
- Automatic reconnection built into EventSource spec

## ADR-006: No Shared Secrets for Frontend Auth

**Decision:** Remove `frontend_id` shared secret. Backend discovers frontends by URL.

**Context:** In v1, a manually configured `frontend_id` had to match between frontend and backend configs. Misconfiguration caused silent failures.

**Consequences:**
- Simpler setup (no secret to configure)
- Backend discovers frontend type via `GET /internal/config`
- Registration uses auto-generated IDs
- Security relies on network isolation (acceptable for on-premise deployment)

## ADR-007: Modular Prompt System

**Decision:** Prompts are separate files editable via admin panel: system, role, mode, context template, post-processing.

**Context:** Different deployments need different prompts. Non-technical admins must be able to customize without code changes.

**Consequences:**
- Admin can customize AI behavior without code
- Prompt assembly is: system + role + mode + context(survey) + RAG
- Stored as markdown files in Docker volume
- Version history not tracked (future improvement)

## ADR-009: Context Compression Without Letta

**Decision:** Implement context compression using the existing LLM with a dedicated summary prompt, instead of integrating Letta/MemGPT.

**Context:** Long conversations can exceed the model's context window. Letta/MemGPT provides sophisticated memory management but requires a separate server (PostgreSQL + Letta container), takes over conversation management, and introduces a fragile external dependency with a fast-moving API.

Our context budget analysis (March 2026):
- Fixed context (system + role + mode + survey + knowledge): ~4,100 tokens
- RAG chunks per message: ~500-1,500 tokens
- Available for conversation at 32K num_ctx: ~26,000 tokens (~40+ exchanges)
- Available at 8K num_ctx: ~2,400 tokens (3-4 exchanges — too tight)

**Approach:**
- Token counter tracks total context size before each LLM call
- When context reaches threshold (configurable, default 70% of num_ctx), compress oldest conversation messages using a dedicated summary prompt
- Summary prompt designed to preserve names, dates, facts, and case data — not the same as end-of-session summary
- System prompt, knowledge base, and recent messages never compressed
- Clean interface (`compress_if_needed`) allows future Letta integration by swapping one function

**Consequences:**
- Zero new dependencies or containers
- Works with any LLM provider already configured
- Compression quality depends on the LLM's summarization ability
- Risk of losing details in compression (mitigated by preservation-focused prompt)
- Letta can be integrated later via Sprint 12 without architectural changes

## ADR-008: Hash-Based Routing (No React Router)

**Decision:** Use `window.location.hash` for routing instead of React Router.

**Context:** Minimal dependency footprint. Only two routes needed: user flow (`/`) and admin (`/#/admin`). Phase transitions managed by React state, not URL.

**Consequences:**
- No react-router dependency
- User flow phases managed by state machine, not URLs
- Admin accessed via hash route
- Deep linking to specific phases not possible (acceptable)
