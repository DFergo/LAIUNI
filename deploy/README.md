# Deployment topologies

The frontend container exposes two surfaces on two ports:

| Container port | Surface | Who uses it | Expose it to |
|---|---|---|---|
| `80` | Public: SPA + browser routes (`/internal/*`) | Users' browsers | Users / a cloudflared public hostname |
| `8080` | Backend: `/backend/v1/*`, every request HMAC-signed | The HRDD backend only | Only a private path to the backend — never the open Internet |

The backend always initiates the connection (pull-inverse): the frontend never needs to know where the backend is. Each frontend has its own signing secret (`HRDD_BACKEND_SECRET`, ≥ 32 characters, e.g. `openssl rand -hex 32`), entered both in the frontend's environment and in **Admin → Frontends** (register or **Security**). The backend registers the URL of the frontend's **backend port**, not the public URL.

| | Where the frontend runs | How the backend reaches port 8080 | Example |
|---|---|---|---|
| **T1** | Another machine on the backend's LAN | `http://<LAN IP>:<FRONTEND_BACKEND_PORT>` (`BACKEND_BIND` = that LAN IP) | [`t1-lan/`](t1-lan/) |
| **T2** | A VPS (no VPN) | `https://<backend hostname>` on a cloudflared tunnel, protected by Cloudflare Access with a service token (sent as extra headers) | [`t2-vps/`](t2-vps/) |
| **T3** | Same machine as the backend, separate containers | `http://hrdd-frontend:8080` over an internal Docker network shared only by the two | [`t3-same-host/`](t3-same-host/) |

One backend can serve frontends in all three topologies at once.

## Requirements common to all topologies

- **Clocks in sync** (NTP) on the backend and frontend hosts: signatures older or newer than ±120 s are rejected.
- The secret lives only in the environment (`.env`, platform secret) and in the backend's registry — never in the repo or the image.
- Rotation without downtime: `HRDD_BACKEND_SECRET=<new>`, `HRDD_BACKEND_SECRET_PREVIOUS=<old>` on the frontend → save the new one in Admin → Frontends → Security → drop the previous one.
- `ALLOW_UNSIGNED_BACKEND_SURFACE=true` disables signature checks. **Development only** — it logs a warning at startup.

## Upgrading an existing frontend

Frontends registered before signing existed keep working with an upgraded backend: they show as **unsigned** in the admin and use the old protocol. To move one to signing:

1. Upgrade the backend.
2. Redeploy the frontend with the new image, `HRDD_BACKEND_SECRET` set and the backend port published (`FRONTEND_BACKEND_PORT`, `BACKEND_BIND`).
3. In Admin → Frontends → **Security**, set the backend-port URL and the same secret **in one save**. The save is verified against the frontend (with the new URL and secret together) before it is stored.

Do steps 2 and 3 back to back: the new frontend image no longer serves the old unsigned routes, so between them the backend can't poll it (users' messages wait in the frontend queue for up to 5 minutes).

## Checks (read-only)

- Public port: `GET /` → 200, `GET /internal/config` → 200, `GET /backend/v1/health` → 404.
- Backend port without a signature: `GET /backend/v1/health` → 401.
- Admin → Frontends shows the frontend **online** and **signed**.
