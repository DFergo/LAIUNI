# HRDD Helper — Installation & Usage Guide

## Prerequisites

- Docker and Docker Compose (v2+)
- macOS or Linux (tested on macOS with Apple Silicon)
- One machine minimum (backend + frontend can share a machine)
- LLM provider: LM Studio or Ollama running and accessible

---

## 1. Clone the Repository

```bash
git clone https://github.com/DFergo/LAIUNI.git
cd LAIUNI
```

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
- `lm_studio_endpoint` / `ollama_endpoint`: Point to your LLM providers. Use `host.docker.internal` if they run on the same machine.
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

### 3.1 Backend

```bash
docker compose -f docker-compose.backend.yml build --no-cache
docker compose -f docker-compose.backend.yml up -d
```

The backend starts on port **8000**. Open `http://localhost:8000` to access the admin panel.

### 3.2 Frontend Worker

```bash
docker compose -f docker-compose.frontworker.yml build --no-cache
docker compose -f docker-compose.frontworker.yml up -d
```

Worker frontend on port **8091**: `http://localhost:8091`

### 3.3 Frontend Organizer

```bash
docker compose -f docker-compose.frontorganizer.yml build --no-cache
docker compose -f docker-compose.frontorganizer.yml up -d
```

Organizer frontend on port **8090**: `http://localhost:8090`

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

1. Start LM Studio or Ollama with your preferred model
2. In admin panel → **LLM** tab, check provider status (should show green/online)
3. Select the model you want to use
4. Adjust temperature, max tokens, context window as needed
5. Click **Save Settings**

### 4.4 Test the Flow

1. Open the worker frontend (`http://localhost:8091`)
2. Select a language
3. Accept the disclaimer
4. Start a new session (note the token)
5. Fill out the survey
6. Send a message — you should see the AI respond in real-time

---

## 5. Multi-Machine Deployment

For production, the backend and frontend(s) run on separate machines.

| Machine | Role | Ports |
|---------|------|-------|
| Backend machine | Backend + LLM | 8000, 1234 (LM Studio), 11434 (Ollama) |
| Frontend machine | Worker + Organizer | 8091, 8090 |

### Network Requirements

- Backend must be able to reach frontend machines via HTTP (polling)
- Frontends do NOT need to reach the backend (pull-inverse architecture)
- Both machines need to resolve each other's IPs

### Docker Compose Overrides

In each `docker-compose.*.yml`, the `DEPLOYMENT_JSON_PATH` environment variable points to the config file. No changes needed unless you want to override defaults.

---

## 6. Rebuilding After Code Changes

```bash
# Clear Docker build cache
docker builder prune -f

# Rebuild specific container
docker compose -f <compose-file> build --no-cache
docker compose -f <compose-file> up -d
```

Replace `<compose-file>` with:
- `docker-compose.backend.yml`
- `docker-compose.frontworker.yml`
- `docker-compose.frontorganizer.yml`

---

## 7. Admin Panel Usage

### Tabs

| Tab | Purpose |
|-----|---------|
| **Frontends** | Register, monitor, enable/disable frontend instances |
| **Prompts** | Edit AI system prompt, role prompts, use case prompts |
| **LLM** | Configure LLM providers, models, parameters |
| **RAG** | Upload reference documents + manage glossary and organizations directory |
| **Sessions** | View active sessions, conversations, flag sessions |
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

See `docs/knowledge/prompt-assembly-flow.md` for the full architecture.

---

## 8. Data & Persistence

All persistent data is stored in Docker volumes at `/app/data` inside each container.

### Backend data (`hrdd-data` volume)

```
/app/data/
├── .admin_hash              # Admin password (bcrypt)
├── .jwt_secret              # JWT signing key
├── frontends.json           # Registered frontends
├── llm_settings.json        # LLM configuration
├── smtp_config.json         # SMTP settings
├── knowledge/
│   ├── glossary.json        # Domain glossary
│   └── organizations.json   # Union directory
├── documents/               # RAG source documents
├── prompts/                 # Editable prompt files
└── sessions/                # Session data (Sprint 8+)
```

### Backup

To back up all data:

```bash
docker cp hrddhelper-hrdd-backend-1:/app/data ./backup_data
```

To restore:

```bash
docker cp ./backup_data/. hrddhelper-hrdd-backend-1:/app/data
```

---

## 9. Troubleshooting

### Backend not polling frontend

- Check that the frontend URL in admin panel uses the host IP (not `localhost`)
- Check that the frontend container is running: `docker compose -f docker-compose.frontworker.yml ps`
- Check backend logs: `docker compose -f docker-compose.backend.yml logs -f`

### LLM not responding

- Verify LM Studio / Ollama is running and the model is loaded
- Check the endpoint in `deployment_backend.json` (use `host.docker.internal` for same-machine)
- Check LLM tab in admin panel — status should show "online"

### Frontend shows "Preparing..." indefinitely

- This can happen on non-HTTPS connections from remote devices (crypto.randomUUID requires secure context)
- Solution: access via `localhost` or set up HTTPS

### Container won't start

```bash
# Check logs
docker compose -f <compose-file> logs

# Full rebuild
docker builder prune -f
docker compose -f <compose-file> build --no-cache
docker compose -f <compose-file> up -d
```

### Reset admin password

Delete the admin hash file and restart:

```bash
docker exec hrddhelper-hrdd-backend-1 rm /app/data/.admin_hash
docker compose -f docker-compose.backend.yml restart
```

Then visit the backend URL to create a new admin account.

---

## 10. Stopping and Removing

```bash
# Stop containers
docker compose -f docker-compose.backend.yml down
docker compose -f docker-compose.frontworker.yml down
docker compose -f docker-compose.frontorganizer.yml down

# Remove data volumes (DESTRUCTIVE — deletes all data)
docker volume rm hrddhelper_hrdd-data
docker volume rm hrddhelper_hrdd-fw-data
docker volume rm hrddhelper_hrdd-fo-data
```
