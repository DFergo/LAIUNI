# Topology B end to end: backend at the union, frontend on a VPS

The whole path in order, with a check after each step. Do not skip a check: each one proves the previous step before the user pays or publishes anything else. Details of each step are in the guides named. Save progress with `profile_save {"step": "..."}` after every block.

What the user does (accounts, payments, clicking links): VPS account and server, Cloudflare account and domain, Tailscale account, opening the Tailscale login link. Everything else you do, asking before each change.

## 1. Backend machine
1. `check_machine`. Docker and Tailscale installed? If not, guide `prerequisites`.
2. Install the backend: guide `install` §1–2 (`deploy_prepare topology="backend"`, `compose up`, `backend_connect`, `admin_create`).
3. Models and embeddings: guide `inference`. Check: `GET /admin/llm/health` answers for the chat slot.
4. `tailscale_status` → this machine is `Running` and has a `100.x.y.z` address. **Check:** state `Running`. Save `{"step": "backend ready"}`.

## 2. The VPS
1. The user rents it (guide `vps`) and gives you `user@address` and tells you which SSH key (path) the server accepts.
2. `remote_check host=user@address` → reachable, Ubuntu/Debian, ≥ 2 GB RAM. **Check:** it answers. If it cannot connect: key not added to the server, wrong address, or port 22 blocked by the provider's firewall.
3. One step at a time, each with the user's yes (`remote_install … apply=true`):
   - `updates`
   - `docker`
   - `tailscale`, then `tailscale_login` → give the user the **login_link**; they open it and approve the machine.
   - `firewall` (optional here: only if the provider has no firewall; the frontend needs no inbound port).
4. `remote_check` again. **Check:** `docker` and `compose` present, `tailscale_ip` is a `100.x.y.z` address, and `listening_beyond_ssh_and_private` is empty.
5. `tailscale_status` on the backend machine. **Check:** the VPS appears as a peer and is `online`. In the Tailscale console, disable key expiry for both machines (guide `prerequisites`). Save `{"step": "vps ready", "vps_tailscale_ip": "..."}`.

## 3. Domain and tunnel
Guide `domain-cloudflare`: a **new dedicated domain** on Cloudflare, a remotely-managed tunnel, the public hostname (e.g. `workers.<domain>`) → `http://hrdd-frontend:80` (only the public port). The tunnel's connector token goes into `~/.config/hrdd-ops/keys.env` as `TUNNEL_TOKEN=…` (the user pastes it there; never in the chat). **Check:** the tunnel exists in Cloudflare (it shows *inactive* until the VPS runs `cloudflared`).

## 4. The frontend on the VPS
1. Prepare locally (secrets are generated or referenced, never shown):
   ```
   deploy_prepare topology="t2-vps-tailscale" folder="~/hrdd/frontend-<site>"
     values={"TAILSCALE_IP": "<vps tailscale ip>",
             "HRDD_BACKEND_SECRET": "env:~/hrdd/backend/.env#HRDD_FRONTEND_SECRET",
             "TUNNEL_TOKEN": "env:~/.config/hrdd-ops/keys.env#TUNNEL_TOKEN"}
   ```
   Show the plan, ask, then `apply=true`.
2. `remote_deploy host=user@address folder="~/hrdd/frontend-<site>"` → plan → ask → `apply=true`. The `.env` is copied straight to the VPS with mode 0600.
3. `remote_compose host=… action="up"` (plan → ask → `apply=true`; the first pull takes a few minutes), then `action="ps"`. **Check:** `hrdd-frontend` and `cloudflared` are *running*; `action="logs" service="cloudflared"` shows the tunnel registered.
4. `check_public_site hostname="workers.<domain>"`. **Check:** `ready: true`. If it does not resolve yet, wait a few minutes (nameservers) and repeat; if HTTPS fails, see `troubleshoot`.
5. `check_frontend public_url="https://workers.<domain>" backend_port_url="http://<vps tailscale ip>:8081"` from the backend machine. **Check:** `all_ok`: the site answers, backend routes are hidden on the public port, and the backend port answers 401 (signed mode) over Tailscale.
Save `{"step": "frontend running"}`.

## 5. Register and configure
Guide `frontends`: register `http://<vps tailscale ip>:8081` (signed), then profiles, languages, texts, branding. **Check:** the frontend shows *online* in `status`.

## 6. Prove it
`test_smoke public_url="https://workers.<domain>"`. **Check:** `ok: true` with a streamed reply. It goes through Cloudflare, the VPS, Tailscale, the backend and the model. Then email (guide `email`) and, if the organization is not UNI, the branding and prompt review in the journey (`overview`). Hand over with guide `operate` (updates: the VPS frontend updates itself at night; backups; rotating secrets). Save `{"step": "installed"}`.

## If something fails
Guide `troubleshoot` (tunnel, Tailscale, signature, offline frontend). Typical T2 causes: Tailscale key expired on the VPS or the backend machine; `TAILSCALE_IP` in the `.env` is not the VPS's current address; the hostname in the tunnel points to a port other than `hrdd-frontend:80`; the secret differs between backend and frontend.
