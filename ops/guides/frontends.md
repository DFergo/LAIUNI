# Frontends: register, configure, brand

A frontend = one website for one audience or campaign. Deploy it first (guide `install`, step 4), then:

## Register (the backend starts polling it)
```
admin_api POST /admin/frontends
  {"url": "<backend-port URL>", "name": "Workers — Spanish garment campaign", "auth_mode": "signed"}
```
- URL by topology: T3 `http://hrdd-frontend:8080` · T1 `http://<LAN IP>:8081` · T2 with Tailscale `http://<VPS tailscale IP>:8081` · T2 without Tailscale `https://<private hostname>` plus `"extra_headers": {"CF-Access-Client-Id": "env:...", "CF-Access-Client-Secret": "env:..."}`.
- With the installation secret (`HRDD_FRONTEND_SECRET` on the backend = `HRDD_BACKEND_SECRET` on the frontend) nothing else is needed. For a frontend on someone else's server, an own secret is safer: generate one, put it in that frontend's `.env` and send `"signing_secret": "env:<that .env>#HRDD_BACKEND_SECRET"`.
- The backend checks the frontend before saving; read the error if it fails (unreachable, signature rejected → secret or clock, wrong port).
- The answer contains the frontend's `id`. `admin_api GET /admin/frontends` shows it **online** within a few seconds.

## Configure (who uses it, languages, login)
A new frontend is **unconfigured** (users see a "not configured" page). Read, change, write back the whole object:
```
admin_api GET /admin/frontends/<id>/config
admin_api PUT /admin/frontends/<id>/config  {<whole config>}
```
Fields:
- `configured`: true.
- `profiles`: subset of `worker`, `representative` (no login by default; for anonymous reporting), `organizer`, `officer` (internal; login by email code by default).
- `auth`: per profile, `true` = email verification code (needs email, guide `email`, and authorised contacts).
- `modes`: per profile — organizer: `documentation`, `interview`, `advisory`, `submit`; officer: the same plus `training`. Worker/representative have no modes.
- `languages`: list of language codes (empty = all). Branding texts are translated automatically into these.
- `display_names`: optional renaming of profiles/modes shown to users.
- `session_resume_window_hours`, `disclaimer_enabled`, `data_protection_email`.
Ask the user what the site is for and propose a config; explain each choice in one line.

## Authorised contacts (profiles with login)
Who may log in: `admin_api GET /admin/contacts`, then `PUT /admin/contacts/global` or `PUT /admin/contacts/frontend/<id>` (see `admin_api_reference filter="contacts"` for fields).

## Branding
```
admin_api GET /admin/frontends/<id>/branding
admin_api PUT /admin/frontends/<id>/branding
  {"app_title": "...", "disclaimer_text": "...", "instructions_text_worker": "...", "logo_mode": "white"}
admin_upload path="/admin/frontends/<id>/branding/logo" file="~/logo.png"
```
Texts are written in English and translated by the translation model into the frontend's languages (`GET .../branding/translation-status`).

## Per-frontend models, prompts, modules, knowledge
- Models only for this frontend: `PUT /admin/frontends/<id>/llm-settings` (only fields that differ from the global settings).
- Campaign documents: `admin_upload path="/admin/rag/upload?frontend_id=<id>"`; campaign knowledge settings: `/admin/rag/campaign/<id>/config`.
- Prompts and modules (e.g. sector-specific instruments): guide `configure`; details in `docs/CAMPAIGN-DEPLOYMENT.md`.

## Check
`check_frontend` and `test_smoke` against the frontend's public address.
