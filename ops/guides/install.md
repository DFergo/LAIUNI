# Installing — step by step with the tools

Every `apply=true` only after the user said yes to the plan you showed.

## 1. Backend
On the backend machine (this machine, normally):
```
deploy_prepare topology="backend" folder="~/hrdd/backend"           → show plan, ask
deploy_prepare ... apply=true                                         → HRDD_FRONTEND_SECRET generated
compose folder="~/hrdd/backend" action="up" apply=true                 → pulls (or builds) and starts
compose folder="~/hrdd/backend" action="logs"                          → wait for "Application startup complete"
```
- For topology C use `t3-same-host` instead (backend + frontend in one folder, one shared secret `HRDD_BACKEND_SECRET`).
- To reach the admin panel from other machines, set `ADMIN_BIND` to this machine's LAN or Tailscale IP (never `0.0.0.0` on an exposed host).
- The first start downloads the images (backend ≈ 1.7 GB): a few minutes on a normal connection.

## 2. Admin account and models
```
backend_connect url="http://127.0.0.1:8000"
admin_create apply=true            → tell the user where the password file is; they store it in their password manager
```
Then the models (guide `inference`): connections, slots, embeddings, `GET /admin/llm/health`.

## 3. Knowledge base
The backend ships with a default knowledge base (international frameworks). Show it: `admin_api GET /admin/rag/documents`. The union can add its own documents (PDF, MD, TXT, JSON): `admin_upload path="/admin/rag/upload" file="..."` (add `?frontend_id=<id>` for one campaign only).

## 4. Frontend(s)
- **T3**: already running in the same folder. Register `http://hrdd-frontend:8080` (guide `frontends`).
- **T1 (other office machine)**: `deploy_prepare topology="t1-lan"` with `HRDD_BACKEND_SECRET="env:~/hrdd/backend/.env#HRDD_FRONTEND_SECRET"` and `BACKEND_BIND=<that machine's LAN IP>`, prepared locally then copied (`scp -r`) to that machine and started there.
- **T2 (VPS)**: `t2-vps-tailscale`, same secret reference, `TAILSCALE_IP=<VPS tailscale IP>`, `TUNNEL_TOKEN` from the tunnel (guide `domain-cloudflare`). Prepare locally, copy to the VPS, start there (guide `vps`).
Then register and configure (guide `frontends`).

## 5. Email
Guide `email`.

## 6. Verify
```
status
check_frontend public_url="http://127.0.0.1:8091"   (or https://<hostname>)
test_smoke public_url="..."
```
A passing smoke test means: frontend → backend polling → model → streamed reply all work. Tell the user it created one test session (token `SMOKE-…`); it can stay or be deleted (`admin_api DELETE /admin/sessions/<token>` with confirmation).

## 7. Hand over
Summarise for the user: addresses (admin panel, each frontend), where the password file is, which models and costs apply, how to update and back up (guide `operate`). Save `profile_save {"step": "installed"}`.
