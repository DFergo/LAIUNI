# HRDD Helper — Installation Guide

> **DRAFT for review. Notes for the reviewer (delete this block before publishing):**
> - This replaces the outdated `docs/INSTALL.md` (it predates the two-port frontend, request signing, `deploy/` topologies, the embeddings slot and the published images). Merge or replace as you see fit; do not keep two installation guides.
> - **Features in flux — update when merged:** the global/per-installation signing secret and the "trusted network: no signature" mode (branch `feat/simple-frontend-registration`). Sections 5.1 and 5.5 describe the per-frontend secret that is merged today and carry a `TODO(builder)` marker.
> - **Please verify before publishing** (written from the code and from one pilot install, not re-run on a clean machine): every command; the UI labels (`Admin → Frontends → Security`, the Embeddings card and its Reindex button); the resource figures in section 3; the health endpoint paths; whether the published backend image is still arm64-only (section 4.1); and the Cloudflare Access steps in section 6, which follow Cloudflare's public documentation and were not re-tested here.
> - Public repo: keep it free of real hostnames, IP addresses, account IDs and secrets. The examples use placeholders.
> - The old guide says "no external API calls, no cloud dependencies". That is no longer true when a cloud model provider is configured; this draft says so explicitly (sections 4.4 and 8).

## 1. What you are installing

HRDD Helper has two kinds of containers:

- **Backend**: the admin panel, the logic, the calls to the language models, and all stored data (sessions, evidence, configuration).
- **Frontend**: the web page users see. You deploy **one frontend per campaign**, each with its own address.

```
 Users' browsers                      Your infrastructure
 ───────────────                      ───────────────────────────────────────────
                    public port (80)           backend port (8080)
   browser  ─────────────►  FRONTEND  ◄───────────────────────────  BACKEND  ──► language models
                         (web + queue)   backend polls, signed       (admin, data)   (local or remote)
```

Three rules shape every deployment:

1. **The backend always initiates the connection** (it polls the frontends). A frontend never contacts the backend and does not know where it is. The backend therefore does not need to be reachable from the Internet.
2. **Each frontend has two ports.** The **public port** (container port `80`) serves the web page and the routes the users' browsers use. The **backend port** (container port `8080`) is used only by the backend. **Never expose the backend port to the open Internet.**
3. **Requests on the backend port are signed** with a secret shared between the backend and that frontend. A request without a valid signature is rejected (`401`). The signature proves *who* is calling; it does not encrypt. On an untrusted network, use an encrypted path (HTTPS through a tunnel, a VPN or an SSH tunnel).

## 2. Choose a deployment

| | Where the frontend runs | How the backend reaches the frontend's backend port | Example |
|---|---|---|---|
| **T1 — Local network** | Another machine on the backend's network | `http://<LAN IP>:<port>` | [`deploy/t1-lan/`](../deploy/t1-lan/) |
| **T2 — Remote server (VPS)** | A server with no VPN to the backend | `https://<private hostname>` through a Cloudflare Tunnel protected by Cloudflare Access | [`deploy/t2-vps/`](../deploy/t2-vps/) |
| **T3 — Same machine** | The same machine as the backend, in separate isolated containers | `http://hrdd-frontend:8080` over an internal Docker network | [`deploy/t3-same-host/`](../deploy/t3-same-host/) |

One backend can serve frontends in all three topologies at once.

How to choose:

- **Trying it out or a small installation:** T3. One machine, one `docker compose up`.
- **A frontend on a different machine in the same office:** T1.
- **A public frontend you want away from your internal network:** T2. A compromised public frontend then sits outside your network, not inside it.
- **Highly sensitive deployments:** prefer a separate machine for the frontends (T1 on an isolated network segment, or T2) over T3.

The model that answers the users can run on the backend machine, on another machine you control, or at a cloud provider. See section 4.4.

## 3. Requirements

- Docker Engine 24 or newer with Docker Compose v2.
- A Linux, macOS or Windows host. The **frontend** image is published for `amd64` and `arm64`.
- **Clocks in sync (NTP) on every machine.** Signatures older or newer than 2 minutes are rejected.
- Memory and disk (observed in a pilot, adjust to your load):
  - Backend: about 0.5 to 1.5 GB of RAM while idle, more if the local embedding model is used; the image is about 1.7 GB, plus your data.
  - Frontend: about 60 MB of RAM each. A server with 2 CPUs and 4 GB of RAM is plenty for several frontends.
- Open only what you need: the public port of the frontends (or a tunnel), nothing else.

## 4. Install the backend

### 4.1 With the published image (recommended)

Create a folder, for example `hrdd-backend/`, with a `compose.yaml`:

```yaml
services:
  hrdd-backend:
    image: ghcr.io/dfergo/laiuni-backend:latest
    pull_policy: always
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - hrdd-data:/app/data
    environment:
      - DEPLOYMENT_JSON_PATH=/app/config/deployment_backend.json
    mem_limit: 3g

volumes:
  hrdd-data:
```

Start it:

```bash
docker compose up -d
docker compose logs --tail 20
```

Notes:

- The admin panel listens on port `8000`. The example publishes it **only on `127.0.0.1`**: reach it from the same machine, or through a VPN, an SSH tunnel or a private network address. If you need a LAN address, bind to that specific address (for example `"192.168.1.10:8000:8000"`), never to every interface on an exposed host.
- Image tags: `latest` follows the `main` branch; `sha-<commit>` pins an exact version; `pilot` is for test builds and should not be used in production.
- The published backend image is built for **`arm64`** only. On an `amd64` host, build from source instead: clone the repository and run `docker compose -f docker-compose.backend.yml up -d --build`.

### 4.2 First run

1. Open `http://127.0.0.1:8000` (or the address you published). You will see **Create Admin Account**.
2. Choose a strong password (at least 8 characters; use a long one). It is stored hashed in the data volume.
3. Log in.

### 4.3 Where the data lives

Everything the backend stores is under `/app/data` in the `hrdd-data` volume: configuration, connections, sessions with their conversations and evidence, RAG indexes, and per-campaign settings. **Back this volume up** (see section 7.2).

### 4.4 Connect the language models

Open **Admin → LLM**. A *connection* is an address plus credentials; a *slot* is a job the system needs a model for. You create connections once and assign them to slots.

**Connection types:** any OpenAI-compatible server (for example LM Studio, vLLM, oMLX, OpenRouter, or OpenAI itself), an Anthropic account, or an Ollama server.

**Slots:**

| Slot | What it does |
|---|---|
| **Inference** | The chat with users. It can have a fallback connection and model that take over if the main one fails. |
| **Reporter** | Internal documents: case file and summaries. |
| **Summariser** | Compresses long conversations. |
| **Translation** | Translates branding and texts. |
| **Embeddings** | Turns documents and questions into vectors for the knowledge base. |

Each slot can use a different connection and model. A frontend can override the global choice (Admin → LLM → per-frontend section).

**Where the model can run.** Anywhere the backend container can reach: the same machine, another machine on your network or VPN, or a cloud provider. Inside the container:

- On Docker Desktop (macOS, Windows), the host machine is `host.docker.internal`.
- On Linux, add `extra_hosts: ["host.docker.internal:host-gateway"]` to the service, or use the host's IP address.

**Privacy.** When a slot uses a cloud provider, the text it processes (user messages, evidence, documents) is sent to that provider. Choose providers and regions that satisfy your data-protection obligations. If everything must stay on your infrastructure, use local or private models for all slots, including embeddings.

**Embeddings (important).**

- Configure a dedicated embeddings connection. A model served by an OpenAI-compatible or Ollama server is recommended. (Anthropic does not provide embeddings.)
- Without an embeddings connection, the backend falls back to a small model that runs inside the container on the CPU (`all-MiniLM-L6-v2`). It works but is weaker and uses extra memory.
- **Changing the embeddings model requires re-indexing**, because vectors from different models are not compatible. Use the **Reindex** button on the Embeddings card. Indexes are kept per connection and model, so switching back to a previous model does not rebuild its index.

After saving the LLM settings the panel shows the status of each connection. Fix anything that is not green before testing.

### 4.5 Email (optional but needed for some profiles)

**Admin → SMTP** configures outgoing email. It is used for the verification codes of profiles that require authentication and for administrator notifications.

## 5. Install a frontend

Do these steps once per frontend (one per campaign).

### 5.1 The signing secret

Each frontend shares a secret with the backend (at least 32 characters). Generate one:

```bash
openssl rand -hex 32
```

It goes in two places: the frontend's `.env` file (as `HRDD_BACKEND_SECRET`) and the backend's registration of that frontend (section 5.5). Keep the `.env` file private (`chmod 600 .env`) and never commit it.

*If you lose it:* nothing is lost. The secret only proves who is calling; it protects no data. Generate a new one and put it in both places (rotation, section 7.4).

*Do not hard-code a secret in files or images:* this repository is public.

<!-- TODO(builder): update 5.1 and 5.5 for the global secret and the trusted-network (no signature) mode once feat/simple-frontend-registration is merged, and say what each mode gives up. -->

### 5.2 T3 — same machine as the backend

```bash
cd deploy/t3-same-host
cp .env.example .env
```

Edit `.env`: set `FRONTEND_PORT` and `HRDD_BACKEND_SECRET` (and the image tags if you want to pin them). Then:

```bash
docker compose up -d
```

This example runs the backend and the frontend together, in separate containers on separate networks. The frontend's backend port is **not published** on the host; the backend reaches it over a private internal network. The frontend has no route to the backend. Register it with the URL `http://hrdd-frontend:8080`.

Residual risk: on that private network the frontend container can open a connection to the backend's admin port, which is protected only by the admin login. Keep the admin password strong, or place the frontends on another machine for sensitive deployments.

### 5.3 T1 — another machine on the same network

```bash
cd deploy/t1-lan
cp .env.example .env
```

Edit `.env`:

- `FRONTEND_PORT`: the public port on this machine.
- `PUBLIC_BIND`: `127.0.0.1` if users arrive through a tunnel on this machine; the machine's LAN address if office users connect directly.
- `BACKEND_BIND`: **this machine's LAN address**, the one the backend can reach. Do not use `0.0.0.0` on a machine with other interfaces.
- `FRONTEND_BACKEND_PORT`: the backend port on this machine.
- `HRDD_BACKEND_SECRET`.

```bash
docker compose up -d
```

Register it with the URL `http://<BACKEND_BIND>:<FRONTEND_BACKEND_PORT>`. Allow that port in the machine's firewall **only from the backend's address**.

### 5.4 T2 — a remote server (VPS)

On the server (Docker installed, only SSH open to the Internet):

```bash
cd deploy/t2-vps
cp .env.example .env
```

Edit `.env`: `HRDD_BACKEND_SECRET` and `TUNNEL_TOKEN` (from the Cloudflare tunnel you create in section 6). Then:

```bash
docker compose up -d
```

The server opens no incoming ports: a Cloudflare Tunnel makes an outgoing connection and publishes two hostnames, one for users and one private hostname for the backend. Section 6 explains how to create them. Register the frontend with the URL `https://<private hostname>`, the secret, and the two Access headers.

### 5.5 Register the frontend in the backend

In **Admin → Frontends**, add a frontend and fill in:

- **URL:** the address of the frontend's **backend port** (not the public address). It depends on the topology, see above.
- **Name:** anything recognisable.
- **Signing secret:** the one from section 5.1.
- **Extra headers** (T2 only): `CF-Access-Client-Id` and `CF-Access-Client-Secret`, from the Cloudflare Access service token.

When you save, the backend **checks that the frontend answers and accepts the signature** before storing it. If it fails, the message tells you why (unreachable, or signature rejected: check the secret and the clocks). A healthy frontend shows as **online** and **signed**.

A frontend starts **unconfigured**: set its profiles, languages, branding and authentication from the backend's frontend settings.

### 5.6 Check it (read-only)

- Public port: `GET /` returns `200`; `GET /internal/config` returns `200`; `GET /backend/v1/health` returns `404` (the public port does not serve the backend routes).
- Backend port, **without** a signature: `GET /backend/v1/health` returns `401`.
- **Admin → Frontends:** the frontend appears **online** and **signed**.

### 5.7 More frontends

Repeat section 5 with a different public port (and a different backend port if the machine is shared), a different project name (`docker compose -p <name>`) and a **different secret**. Each frontend has its own data volume.

## 6. Public access with a Cloudflare Tunnel

A tunnel lets users reach a frontend without opening any incoming port. In the Cloudflare Zero Trust dashboard:

1. **Create a tunnel** (remotely managed) and copy its token into the frontend's `TUNNEL_TOKEN`.
2. **Public hostname for users:** point `https://<users hostname>` to `http://hrdd-frontend:80` (the service name in the compose network), or to `http://localhost:<FRONTEND_PORT>` if `cloudflared` runs on the host. **Map only the public port here.**
3. **Private hostname for the backend (T2):** point `https://<private hostname>` to `http://hrdd-frontend:8080`.
4. **Protect the private hostname with Cloudflare Access:** create a *service token*, then a self-hosted Access application for the private hostname with a single policy of type **Service Auth** that includes only that token. Enable **Protect with Access** on that hostname in the tunnel so that `cloudflared` validates the Access credential. Copy the token's client ID and secret (shown once) into the backend's extra headers.
5. Create the DNS records for the two hostnames pointing to the tunnel.

If you do not use Cloudflare, any reverse proxy that terminates HTTPS in front of the **public port** works. Whatever you use, **never publish the backend port to the open Internet.**

## 7. Operate it

### 7.1 Updates

```bash
docker compose pull
docker compose up -d
```

To update automatically, add the label `com.centurylinklabs.watchtower.enable=true` to the service and run Watchtower with `--label-enable` on a nightly schedule, so only labelled containers are touched. With a recent Docker Engine the classic Watchtower image needs `DOCKER_API_VERSION=1.44` (otherwise it fails with "client version is too old").

Use `latest` for production, or pin `sha-<commit>` and update on purpose. Test builds are tagged `pilot`.

To roll back, set the previous `sha-<commit>` tag in the compose file and run `docker compose up -d`.

### 7.2 Back up

- **The data volume** (a consistent copy of everything):

  ```bash
  docker run --rm -v hrdd-data:/data -v "$PWD":/backup alpine tar czf /backup/hrdd-data.tgz -C /data .
  ```

  Stop the backend first if you need a perfectly consistent copy.
- **Configuration only:** Admin → Frontends → **Global Config Backup** exports and imports the whole `config/`. After importing, **restart the backend**.
- **Per frontend:** Export ZIP / Import ZIP of one campaign (configuration, branding, translations, prompts, RAG sources; RAG indexes are rebuilt).
- Frontends keep only transient queues. There is nothing to back up there beyond their `.env` file.

### 7.3 Logs and health

```bash
docker compose logs --tail 100
docker compose ps
```

The backend answers `GET /api/v1/health`.

### 7.4 Rotate a frontend's secret without downtime

1. On the frontend, put the new value in `HRDD_BACKEND_SECRET` and the old value in `HRDD_BACKEND_SECRET_PREVIOUS`, then `docker compose up -d`.
2. In **Admin → Frontends → Security**, save the new secret for that frontend.
3. Empty `HRDD_BACKEND_SECRET_PREVIOUS` and run `docker compose up -d` again.

### 7.5 Reset the admin password

```bash
docker compose exec hrdd-backend rm /app/data/.admin_hash
docker compose restart hrdd-backend
```

Then open the admin panel and create a new account.

## 8. Security checklist

- [ ] The backend's admin port is not published on an untrusted network.
- [ ] No frontend publishes its backend port to the open Internet.
- [ ] Each frontend has its own secret of at least 32 random characters, kept in a private `.env` and never committed.
- [ ] Users reach the frontends only through HTTPS.
- [ ] Clocks are synchronised on all machines.
- [ ] The admin password is long and unique.
- [ ] The data volume is backed up.
- [ ] You know which model providers are local and which are cloud, and your data-protection obligations are met for each.
- [ ] Only the machine's administration port is open to the Internet on a remote server, restricted to key-based login.
- [ ] Updates are applied regularly (or automated for labelled containers).

## 9. Troubleshooting

**The frontend is registered but shows offline, or the backend says "Cannot reach frontend".**
Check that the URL is the frontend's **backend port** address and that the backend machine can reach it (`curl` from the backend host). In T2, check the tunnel is running and the Access headers are correct.

**"Rejected the signature" (HTTP 401).**
The secret differs between the frontend and the backend, or the clocks are more than about 2 minutes apart. Check both, and synchronise time (NTP).

**The backend does not pick up users' messages.**
Check the frontend is **enabled** in the admin and online, and read the backend logs.

**A language model does not answer.**
Check the connection status in **Admin → LLM**. If a slot shows "Down", the circuit breaker tripped after repeated failures and retries by itself after a few minutes. From inside the container, `host.docker.internal` only works on Docker Desktop, or on Linux with the `extra_hosts` entry.

**Embeddings errors, or poor retrieval after a change.**
You changed the embeddings model: use **Reindex** on the Embeddings card.

**The frontend shows "Preparing…" for ever on a remote device.**
Browsers require HTTPS (a secure context) on remote devices. Serve the frontend over HTTPS.

**The backend uses a lot of memory.**
The local embedding fallback is active. Configure an embeddings connection (section 4.4).

## 10. Stop and remove

```bash
docker compose down
```

This keeps the data. To delete the data as well (irreversible), remove the volumes: `docker compose down -v`.

## Appendix: ports and variables

| Item | Container port | Default | Who uses it |
|---|---|---|---|
| Backend admin panel and API | `8000` | published on `127.0.0.1:8000` in the example | Administrator |
| Frontend public surface | `80` | `FRONTEND_PORT` / `PUBLIC_BIND` | Users' browsers |
| Frontend backend surface | `8080` | `FRONTEND_BACKEND_PORT` / `BACKEND_BIND` | The backend only |

| Variable | Where | Meaning |
|---|---|---|
| `HRDD_BACKEND_SECRET` | frontend | Signing secret shared with the backend (at least 32 characters) |
| `HRDD_BACKEND_SECRET_PREVIOUS` | frontend | Old secret, accepted while rotating |
| `FRONTEND_PORT`, `PUBLIC_BIND` | frontend | Public port and the address it listens on |
| `FRONTEND_BACKEND_PORT`, `BACKEND_BIND` | frontend | Backend port and the address it listens on (T1) |
| `TUNNEL_TOKEN` | frontend (T2) | Cloudflare Tunnel token |
| `FRONTEND_TAG`, `BACKEND_TAG` | compose | Image tag to run |
| `ALLOW_UNSIGNED_BACKEND_SURFACE` | frontend | Disables signature checks. Development only; logs a warning at startup |
| `DEPLOYMENT_JSON_PATH` | backend | Path of the deployment configuration file inside the container |
