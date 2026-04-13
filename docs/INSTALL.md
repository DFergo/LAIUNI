# HRDD Helper — Installation & Usage Guide

## Prerequisites

- Docker and Docker Compose (v2+)
- macOS, Linux, or Windows
- One machine minimum (backend + frontend can share a machine)
- LLM provider: Ollama (recommended for production) or LM Studio

---

## 1. Clone the Repository

```bash
git clone https://github.com/DFergo/LAIUNI.git
cd LAIUNI
```

Or deploy directly from GitHub via Portainer (see section 3.2).

---

## 2. Configuration

### 2.1 Backend Configuration

Edit `config/deployment_backend.json`:

```json
{
  "role": "backend",
  "lm_studio_endpoint": "http://host.docker.internal:1234/v1",
  "lm_studio_model": "qwen3-235b-a22b",
  "ollama_endpoint": "http://host.docker.internal:11434",
  "poll_interval_seconds": 2,
  "streaming_enabled": true,
  "guardrails_enabled": true,
  "guardrail_max_triggers": 3
}
```

Key settings:
- `lm_studio_endpoint` / `ollama_endpoint`: Point to your LLM providers. Use `host.docker.internal` if they run on the same machine as Docker.
- `poll_interval_seconds`: How often the backend polls frontends for messages. Lower = faster response, more CPU.

### 2.2 Frontend Configuration

Worker: `config/deployment_frontend_worker.json`
Organizer: `config/deployment_frontend_organizer.json`

```json
{
  "role": "frontend",
  "frontend_type": "worker",
  "session_resume_window_hours": 48,
  "disclaimer_enabled": true,
  "auth_required": false
}
```

- `frontend_type`: `worker` or `organizer`
- `auth_required`: `true` for organizer (email verification), `false` for worker
- `session_resume_window_hours`: How long a session token remains valid

---

## 3. Build and Run

### 3.1 Command Line (Docker Compose)

**Backend:**

```bash
docker compose -f docker-compose.backend.yml build --no-cache
docker compose -f docker-compose.backend.yml up -d
```

The backend starts on port **8000**. Open `http://localhost:8000` to access the admin panel.

**Frontend Worker (port 8091):**

```bash
docker compose -f docker-compose.frontworker.yml build --no-cache
docker compose -f docker-compose.frontworker.yml up -d
```

**Frontend Organizer (port 8090):**

```bash
docker compose -f docker-compose.frontorganizer.yml build --no-cache
docker compose -f docker-compose.frontorganizer.yml up -d
```

### 3.2 Portainer (Recommended)

Portainer gives you a web UI to manage, rebuild, and monitor stacks.

1. In Portainer → **Stacks** → **Add Stack**
2. Select **Repository**
3. For each stack:

| Stack name | Repository URL | Branch | Compose path |
|---|---|---|---|
| `hrdd-backend` | `https://github.com/DFergo/LAIUNI` | `main` | `docker-compose.backend.yml` |
| `hrdd-frontworker` | `https://github.com/DFergo/LAIUNI` | `main` | `docker-compose.frontworker.yml` |
| `hrdd-frontorganizer` | `https://github.com/DFergo/LAIUNI` | `main` | `docker-compose.frontorganizer.yml` |

4. Click **Deploy the stack**

To update after code changes: **Pull and Redeploy** from the stack page in Portainer.

---

## 4. First Run Setup

### 4.1 Admin Account

1. Open `http://localhost:8000` (or the backend machine's IP)
2. You'll see "Create Admin Account" — set a password (min 8 characters)
3. Log in with the password you just created

### 4.2 Register Frontends

1. In the admin panel, go to **Frontends** tab
2. Click **Add Frontend**
3. Enter the frontend URL:
   - Same machine: `http://<HOST_IP>:8091` (worker) or `http://<HOST_IP>:8090` (organizer)
   - Different machine: `http://<FRONTEND_IP>:8091`
   - **Important:** Use the host machine's IP, not `localhost` or Docker internal addresses
4. The backend will auto-discover the frontend type and name
5. Make sure the frontend is **Enabled** (toggle on)

### 4.3 LLM Provider

1. Start Ollama or LM Studio with your preferred model(s)
2. In admin panel → **LLM** tab, check provider status (should show green/online)
3. Select the provider and model for each slot (Inference, Reporter, Context Compression)
4. Adjust temperature, max tokens, context window as needed
5. Click **Save Settings**

When you save settings with Ollama models, the backend automatically sends a warmup request to pre-load each model into VRAM. This avoids cold-start delays on the first user message.

### 4.4 Test the Flow

1. Open the worker frontend (`http://<HOST_IP>:8091`)
2. Select a language
3. Accept the disclaimer
4. Start a new session (note the token)
5. Fill out the survey
6. Send a message — you should see the AI respond in real-time

---

## 5. Ollama Setup & Performance

### 5.1 Installing Ollama

Ollama runs outside Docker, directly on the host machine.

- **macOS:** `brew install ollama` or download from [ollama.com](https://ollama.com)
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`
- **Windows:** Download installer from [ollama.com](https://ollama.com)

Ollama starts automatically on login (macOS/Windows) or as a systemd service (Linux).

### 5.2 Downloading Models

```bash
# Recommended production setup
ollama pull gemma3:27b          # Inference (chat) — ~20 GB
ollama pull qwen3.5:35b         # Reporter (documents) — ~22 GB
ollama pull qwen3.5:9b          # Summariser (compression) — ~7 GB
```

Models are only loaded into VRAM when first used (or when the admin saves LLM settings — the backend sends a warmup request automatically).

### 5.3 Concurrency — OLLAMA_NUM_PARALLEL

By default, Ollama processes **one request at a time per model**. With multiple concurrent users, requests queue up and wait. Each chat response takes 10-30 seconds, so with 10+ users this becomes a bottleneck.

**Solution:** Set `OLLAMA_NUM_PARALLEL` to allow multiple simultaneous requests to the same model.

**macOS:**

```bash
launchctl setenv OLLAMA_NUM_PARALLEL 4
```

Then restart Ollama. To make it permanent, add to `~/.zshrc` or `~/.bash_profile`:

```bash
export OLLAMA_NUM_PARALLEL=4
```

**Linux (systemd):**

```bash
sudo systemctl edit ollama
```

Add:

```ini
[Service]
Environment="OLLAMA_NUM_PARALLEL=4"
```

Then `sudo systemctl restart ollama`.

**Windows:**

Set as a system environment variable: `OLLAMA_NUM_PARALLEL=4`, then restart Ollama.

**How to choose the value:**
- Each parallel slot uses additional VRAM for its KV cache context
- With 512 GB unified memory: `4-8` is comfortable
- With 64 GB: `2-3` is safe
- With 32 GB or less: leave at `1` (default)
- Only the inference model (chat) benefits from parallelism — reporter and summariser have low concurrency

### 5.4 Keep-Alive

By default, Ollama unloads models from VRAM after 5 minutes of inactivity. For a production deployment with regular traffic, increase this:

```bash
# macOS
launchctl setenv OLLAMA_KEEP_ALIVE "24h"

# Linux (systemd edit)
Environment="OLLAMA_KEEP_ALIVE=24h"
```

This keeps models in VRAM for 24 hours after the last request, avoiding cold-start delays.

### 5.5 Prompt Caching (Automatic)

Ollama automatically caches the KV state (prompt cache) for each conversation. When a user sends a new message, Ollama reuses the cached computation from previous turns and only processes the new message. This dramatically reduces Time To First Token (TTFT) on subsequent turns.

The cache is per-model and per parallel slot. It works best when:
- `OLLAMA_NUM_PARALLEL` is set (each slot maintains its own cache)
- `OLLAMA_KEEP_ALIVE` is long enough to prevent model unloading
- Context compression is infrequent (compression invalidates the cache)

No configuration needed — it's automatic.

### 5.6 VRAM Planning

| Component | VRAM approx |
|---|---|
| Gemma 4 27B (inference) | ~20 GB |
| Qwen 3.5 35B (reporter) | ~22 GB |
| Qwen 3.5 9B (summariser) | ~7 GB |
| KV cache per parallel slot | ~2-4 GB per slot (depends on context length) |
| **Example: 3 models + 4 parallel slots** | **~65 GB** |

Apple Silicon (M3 Ultra 512 GB): plenty of headroom.
Dedicated GPU servers: size according to available VRAM.

---

## 6. LLM Slot Architecture

HRDD Helper uses **three LLM slots**, each configurable independently in the admin panel:

| Slot | Purpose | Recommended Model |
|---|---|---|
| **Inference** | Chat with users | Gemma 4 (conversational, vision-capable) |
| **Reporter** | Internal documents (case file, UNI summary) | Qwen 3.5 35B (structured, factual) |
| **Summariser** | Context compression for long conversations | Qwen 3.5 9B (small, fast) |

### Fallback Cascade

If a model fails (crash, timeout, zero tokens), the system automatically falls back:

- **Summariser** fails → tries Reporter → tries Inference → error
- **Reporter** fails → tries Inference → error
- **Inference** fails → error (no fallback — it's the primary model)

The circuit breaker tracks failures: 3 failures in 60 seconds marks a slot as "down" for 5 minutes. Down slots are skipped instantly. After 5 minutes the slot is retried automatically.

### Admin Notifications

When a fallback is activated, the admin receives an email (if SMTP is configured). Rate-limited to 1 email per slot per hour.

### Per-Frontend LLM Override

Each registered frontend can override the global LLM settings. In admin → **LLM** tab → **Per-Frontend LLM** section, you can assign different models to different frontends. Useful when one frontend needs a larger/faster model than another.

---

## 7. Multi-Machine Deployment

For production, the backend and frontend(s) typically run on separate machines.

| Machine | Role | Ports |
|---------|------|-------|
| Backend machine | Backend + Ollama/LM Studio | 8000, 11434 (Ollama), 1234 (LM Studio) |
| Frontend machine | Worker + Organizer | 8091, 8090 |

### Network Requirements

- Backend must be able to reach frontend machines via HTTP (polling)
- Frontends do NOT need to reach the backend (pull-inverse architecture)
- Users access the frontend machine directly via browser
- The admin panel is on the backend machine (`:8000`)

### Docker Compose Overrides

In each `docker-compose.*.yml`, the `DEPLOYMENT_JSON_PATH` environment variable points to the config file. For multi-machine, edit `deployment_backend.json` to use the actual Ollama/LM Studio host IP instead of `host.docker.internal`.

---

## 8. Admin Panel

### Tabs

| Tab | Purpose |
|-----|---------|
| **Frontends** | Register, monitor, enable/disable frontend instances |
| **Prompts** | Edit AI system prompt, role prompts, use case prompts |
| **LLM** | Configure LLM providers, models, parameters per slot |
| **RAG** | Upload reference documents + manage glossary and organizations directory |
| **Sessions** | View active sessions, conversations, flag sessions, generate/download reports |
| **SMTP** | Configure email for notifications and auth codes |

### Knowledge Base (RAG Tab)

The RAG tab has three sections:

1. **RAG Documents**: Upload ILO conventions, OECD guidelines, etc. These are indexed and retrieved by relevance during conversations.
2. **Glossary**: Domain terms with definitions and translations. Injected directly into every session for consistent terminology.
3. **Organizations Directory**: Curated list of unions, federations, and institutions. The AI only references organizations from this list.

### Prompts

Prompts are modular. The system loads them in layers:
1. Core system prompt → defines AI identity and constraints
2. User prompt → adapts tone to the user's role (worker/organizer/etc.)
3. Use case prompt → defines conversation mode (documentation/advisory/training)
4. Context template → injects survey data
5. Knowledge base → glossary + organizations

---

## 9. Data & Persistence

All persistent data is stored in Docker volumes at `/app/data` inside each container.

### Backend data (`hrdd-data` volume)

```
/app/data/
├── .admin_hash              # Admin password (bcrypt)
├── .jwt_secret              # JWT signing key
├── frontends.json           # Registered frontends
├── llm_settings.json        # LLM configuration
├── smtp_config.json         # SMTP settings
├── authorized_emails.json   # Authorized users (organizer)
├── knowledge/
│   ├── glossary.json        # Domain glossary
│   └── organizations.json   # Union directory
├── documents/               # RAG source documents
├── rag_index/               # LlamaIndex vector store
├── prompts/                 # Editable prompt files
├── campaigns/               # Per-frontend overrides (prompts, LLM, branding, notifications)
└── sessions/                # Session data (conversations, evidence, reports)
    └── <session_token>/
        ├── session.json
        ├── conversation.jsonl
        ├── evidence/
        ├── evidence_context.json
        ├── summary.md
        ├── session_summary_uni.md
        └── internal_case_file.md
```

### Backup

```bash
# Find the volume name
docker volume ls | grep hrdd

# Copy data out
docker cp <backend-container-name>:/app/data ./backup_data

# Restore
docker cp ./backup_data/. <backend-container-name>:/app/data
```

### Frontend data

Frontend volumes (`hrdd-fw-data`, `hrdd-fo-data`) store branding translations and sidecar state. They are ephemeral and can be recreated by redeploying.

---

## 10. Rebuilding After Code Changes

### Command Line

```bash
docker builder prune -f
docker compose -f <compose-file> build --no-cache
docker compose -f <compose-file> up -d
```

### Portainer

In the stack page, click **Pull and Redeploy**. Portainer pulls the latest code from GitHub and rebuilds.

---

## 11. Troubleshooting

### Backend not polling frontend

- Check that the frontend URL in admin panel uses the host IP (not `localhost`)
- Check that the frontend container is running
- Check backend logs: `docker logs <backend-container-name> --tail 50`

### LLM not responding

- Verify Ollama is running: `ollama ps` (shows loaded models)
- Check the endpoint in `deployment_backend.json` (use `host.docker.internal` for same-machine Docker)
- Check LLM tab in admin panel — status should show green/online
- If a slot shows "Down" or "Degraded" badge, the circuit breaker has tripped — check Ollama logs

### Frontend shows "Preparing..." indefinitely

- This happens on non-HTTPS connections from remote devices (`crypto.randomUUID` requires secure context)
- Solution: access via `localhost`, or set up HTTPS with a reverse proxy

### Slow first response (cold start)

- Ollama needs to load the model into VRAM on first request (~10-60s depending on model size)
- Solution: save LLM settings in admin panel — this triggers a warmup request that pre-loads models
- Set `OLLAMA_KEEP_ALIVE=24h` to prevent automatic unloading

### Reset admin password

```bash
docker exec <backend-container-name> rm /app/data/.admin_hash
docker restart <backend-container-name>
```

Then visit the backend URL to create a new admin account.

---

## 12. Stopping and Removing

### Command Line

```bash
# Stop containers (preserves data)
docker compose -f docker-compose.backend.yml down
docker compose -f docker-compose.frontworker.yml down
docker compose -f docker-compose.frontorganizer.yml down

# Remove data volumes (DESTRUCTIVE — deletes all data)
docker volume rm <volume-name>
```

### Portainer

Stop or remove stacks from the Stacks page. Volumes are preserved unless you delete them explicitly in **Volumes**.

---

## 13. Security Notes

- The admin panel is password-protected (bcrypt + JWT)
- The organizer frontend can require email verification (auth codes via SMTP)
- Frontends never know where the backend is (pull-inverse architecture)
- All data stays on your infrastructure — no external API calls, no cloud dependencies
- The LLM runs locally (Ollama/LM Studio) — no data leaves the network
