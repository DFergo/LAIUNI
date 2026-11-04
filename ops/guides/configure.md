# Configuration areas (admin panel ↔ API)

Log in first (`backend_connect`, `login`). `admin_api_reference filter="<area>"` lists the exact endpoints and fields of the running version. Read the current value before changing it, show the change, ask, apply.

| Area | Endpoints (prefix `/admin`) | Notes |
|---|---|---|
| Frontends | `/frontends`, `/frontends/{id}`, `/{id}/config`, `/{id}/branding`, `/{id}/branding/logo` | guide `frontends`. `DELETE /frontends/{id}` moves it to *deleted* (restorable: `/frontends/deleted`, `/{id}/restore`). |
| Models | `/llm/connections`, `/llm/settings`, `/llm/health`, `/llm/models`, `/llm/capabilities`, `/llm/usage`, `/llm/embedding/reindex`, `/frontends/{id}/llm-settings` | guide `inference`. `/llm/usage` shows tokens and prompt-cache rate. |
| Knowledge base | `/rag/documents`, `/rag/upload`, `/rag/documents/{name}`, `/rag/reindex`, `/rag/stats`, `/rag/campaign/{id}/config`, `/rag/reset-defaults` | Uploads: `admin_upload`. Reset restores the shipped documents (destructive). |
| Glossary, organisations | `/knowledge/glossary`, `/knowledge/organizations`, `/knowledge/settings`, `/knowledge/frontend/{id}`, `/knowledge/frontend/{id}/glossary` and `/organizations` | Terms and reference organisations added to the assistant's prompt. Global switch `{"glossary_enabled", "organizations_enabled"}`; per frontend `{"mode": "global" / "off" / "custom", "items": [...]}` — e.g. a campaign with one or two reference unions gets its own short list. |
| Prompts | `/prompts`, `/prompts/{name}`, `/prompts/{name}/preview`, `/prompts/frontend/{id}/source`, `/prompts/reset` | The assistant's instructions. Change only with care; `reset` restores the defaults of one prompt. Campaign prompts: `docs/CAMPAIGN-DEPLOYMENT.md`. |
| Modules | `/modules`, `/modules/frontend/{id}` | Optional sector modules (e.g. FSC) per frontend. |
| Email | `/smtp`, `/smtp/test`, `/smtp/authorized-emails`, `/smtp/frontend-notifications/{id}` | guide `email`. |
| Contacts | `/contacts`, `/contacts/global`, `/contacts/frontend/{id}`, `/contacts/export`, `/contacts/import` | Who may log in / receive reports. |
| Sessions | `/sessions` (list), `/sessions/lifecycle`, `/sessions/resume-windows`, `/sessions/{token}` (**content**), `/sessions/{token}/documents` (**reports**), `/sessions/purge/{id}` (destructive) | Auto-close and auto-cleanup per frontend in `lifecycle`. |
| Portability | `/export/global`, `/export/frontend/{id}`, `/import/global`, `/import/frontend/{id}` | Backups and moving configuration between installations (exports may contain content). |

## Content and reports
`/sessions/{token}` and `/sessions/{token}/documents` return what workers wrote and the internal reports. Use only when the user asks for something that needs it; ask each time (`confirm_content=true`). Prefer summaries in the chat over quoting.

## Typical requests
- "Add Portuguese to the workers site" → GET config, add `pt` to `languages`, PUT; branding is translated automatically.
- "Use another model for the reports" → connection if new, then `PUT /llm/settings {"reporter_connection": ..., "reporter_model": ...}`, `GET /llm/health`.
- "Close inactive sessions after 4 hours" → `PUT /sessions/lifecycle/{id}`.
- "How much are we spending?" → `GET /llm/usage` (tokens per slot and model; prices are on the provider's site).
