# Troubleshooting

Read-only checks first, then explain, then propose a fix (and ask).

## First look
- `status` — frontends (online/offline, mode badge), model health, embeddings, knowledge base, email.
- `compose action="ps"` / `action="logs"` in the backend folder (and the frontend's, if local).
- `check_frontend` with the public URL (and backend-port URL if reachable from here).

## Symptoms
| Symptom | Likely cause | Check / fix |
|---|---|---|
| Admin panel does not open | Container not running; wrong address; `ADMIN_BIND` | `compose ps`, `compose logs`; open `http://127.0.0.1:8000` on the backend machine. |
| Frontend **offline** in the admin | Backend cannot reach the backend port | From the backend machine: `curl -s -o /dev/null -w '%{http_code}' <url>/backend/v1/health` → 401 means reachable (signed). Timeout: IP/port, `BACKEND_BIND`, Tailscale (`tailscale status`, key expiry), firewall. |
| Registration: "signature rejected" | Different secrets, or clocks out of sync (±120 s) | Same value in backend `HRDD_FRONTEND_SECRET` and frontend `HRDD_BACKEND_SECRET` (compare masked lengths with `env_show`; never print). Enable NTP on both machines. |
| "frontend accepts unsigned" badge | Frontend runs with `BACKEND_SURFACE_AUTH=trusted-network` | Set `signed` and the secret, restart. |
| Site shows "not configured" | Config not saved | guide `frontends` → `configured: true`, profiles. |
| Users get no reply / error | Model down, wrong key, no credit | `GET /admin/llm/health`; provider console (credit, key); `test_smoke` for the exact error. |
| Slow replies | Large model on a small machine; cloud provider load; embeddings on CPU fallback | `GET /admin/llm/embedding-health`; configure local GPU embeddings (guide `inference`); smaller/faster model. |
| Knowledge base answers poor after a model change | Embeddings changed without reindex | `POST /admin/llm/embedding/reindex`. |
| No login codes by email | SMTP not configured / failing; address not authorised | `POST /admin/smtp/test`; contacts (guide `frontends`). |
| Tunnel site down (Cloudflare error 1033/502) | `cloudflared` not running or wrong service in the hostname | `compose ps` on the VPS; the hostname must point to `http://hrdd-frontend:80`. |
| T2 frontend container does not start after reboot | Tailscale IP not up yet when Docker started | `docker compose up -d` again; ensure Tailscale starts at boot (`systemctl enable tailscaled`). |
| Backend does not start / is killed | Not enough memory or disk | ≥ 8 GB RAM (the backend container is limited to 3 GB), ≥ 10 GB free disk; `compose logs`. |

## Never
- Call `GET /backend/v1/queue` on a frontend by hand (it consumes users' messages).
- Publish the frontend backend port or the admin port on the open Internet as a "fix".
- Delete volumes (`docker compose down -v`, `docker volume rm`) — that deletes all data.
