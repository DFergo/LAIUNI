# HRDD Helper — Changelog

## v2.0 — Clean Rewrite

### Sprint 18 — Authorized contacts directory: extended fields + Excel import/export + per-frontend override (2026-04-13)

- **New data model** (`smtp_service.py`): legacy `authorized_emails.json` (flat list) replaced by `authorized_contacts.json` with structure `{global: Contact[], per_frontend: {fid: {mode: "replace"|"append", contacts: Contact[]}}}`. Each `Contact` has 7 fields: `email` (primary key, normalised lowercase/trim), `first_name`, `last_name`, `organization`, `country`, `sector`, `registered_by`.
- **Automatic migration**: on first read, if `authorized_emails.json` exists and `authorized_contacts.json` does not, `_migrate_authorized_emails_if_needed()` converts every email to an empty Contact (extra fields blank) and renames the legacy file to `authorized_emails.json.bak`. Idempotent.
- **Per-frontend override resolution**: new `is_email_authorized(email, frontend_id=None)` resolves the effective set — no fid or unknown fid → global; `mode="replace"` → only per-frontend; `mode="append"` → union. Legacy `is_email_authorized(email)` wrapper still resolves to global.
- **Callers updated**: `polling._finalize_session` and `_handle_auth_request` now thread `frontend_id` through.
- **New admin endpoints** (`api/v1/admin/contacts.py`): `GET /admin/contacts`, `PUT /admin/contacts/global`, `PUT /admin/contacts/frontend/{fid}`, `DELETE /admin/contacts/frontend/{fid}`, `POST /admin/contacts/frontend/{fid}/copy-from/{src_fid}?mode=...`, `GET /admin/contacts/export?scope=...` (streams `.xlsx`), `POST /admin/contacts/import?scope=...` (accepts `.xlsx` or `.csv`, **additive merge only** — existing emails get field updates, new emails added, emails in backend but not in file preserved). Import returns `{added, updated, ignored_malformed}`.
- **Dependency**: `openpyxl>=3.1` added to `requirements.txt` (~5 MB).
- **Tests** (`src/backend/tests/test_authorized_contacts.py`): unittest suite (stdlib only, no pytest). Covers empty store, global-only, mode=replace, mode=append, invalid email rejection, legacy migration, backward-compat wrappers, save roundtrip normalisation. Run: `python -m unittest src.tests.test_authorized_contacts -v`.
- **Admin UI** — new top-level tab **Registered Users** (`Dashboard.tsx`, `RegisteredUsersTab.tsx`): scope selector (Global / per frontend, with `◆ custom` marker); editable table with all 7 fields, inline editing; **sortable** — every column header clicks to toggle asc/desc, preference persisted in localStorage per scope; text filter across all fields; Add/Delete rows; Save (only when dirty); Export `.xlsx` via authenticated fetch + blob download; Import `.xlsx`/`.csv` with post-import summary. Per-frontend scope: mode toggle (replace/append), "Copy from" dropdown listing frontends with overrides, "Remove override" button.
- **SMTP tab cleanup**: old "Authorized Emails" section replaced by a pointer to the new tab. Legacy API preserved for backward compatibility.
- Merges backlog ideas #6 (extended-fields directory + Excel I/O) and #11 (per-frontend lists with replace/append + copy-from) into a single sprint to avoid migrating the JSON twice.

### Sprint 17 — LLM resilience: fallback cascade, Ollama warmup, email alerts, health badges (2026-04-12)

- **Fallback cascade** (`llm_provider.py`): new `stream_chat_with_fallback()` and `chat_with_fallback()` try slots in order (summariser → reporter → inference). Deduplicates slots that resolve to the same provider:model. All call sites updated: `evidence_processor.summarise_document`, `polling._generate_document`, `polling._finalize_session`, `context_compressor._compress_messages`. Chat inference intentionally has no fallback.
- **Circuit breaker**: per-slot failure tracking (`_slot_failures` dict). 3 failures in 60s → slot marked "down" for 5 min. Down slots skipped immediately (no wasted latency). Auto-recovery after cooldown. `get_slot_health()` exposes state to admin panel.
- **`slot_settings()` + `build_fallback_chain()`**: moved slot resolution from `polling.py` to `llm_provider.py` as shared module-level helpers. All callers use `build_fallback_chain(settings, primary_slot)`.
- **Email notification** (`smtp_service.py`): `notify_slot_failure()` sends admin email on degradation (fallback active) or offline (all slots exhausted). Rate-limited to 1 per slot per hour. Wired from `stream_chat_with_fallback` via fire-and-forget `asyncio.create_task`.
- **Ollama warmup on config save** (`admin/llm.py`): `_warmup_ollama_slots()` sends a `max_tokens=1` completion to each Ollama slot as a background task when admin saves LLM settings. Forces model pre-load into VRAM. 120s timeout. Skips LM Studio slots. Also runs on per-frontend override save.
- **Health badges** (`LLMTab.tsx`): `slotBadge()` renders "Down" (red pill) or "Degraded" (amber pill) next to slot headers. Data comes from `slot_health` in the `/admin/llm/health` response (polled every 15s). No badge when healthy.
- Backend only — no frontend container changes.

### Sprint 16 — Claude-style attachment chips + ship-with-prompt + retraction (2026-04-11 → 2026-04-12)

**Hotfixes applied on 2026-04-12 during acceptance testing (backend-only, no frontend rebuild needed):**
- `evidence_processor.summarise_document` now raises `RuntimeError` when the summariser LLM returns zero tokens (model crash, eviction from LM Studio, context overflow, empty `<think>…</think>` blocks). Previously the empty string was silently written to `evidence_context.json`, the chip went to `ready` (false positive), and the user had no way to know the summary had failed. Now the exception propagates up to `_handle_upload`, which emits `upload_error` → frontend chip goes to `error` state. The file stays on disk for audit but is NOT indexed into RAG or evidence_context (safe to retry).
- `evidence_processor.process_upload` now deduplicates by filename at the start: if an entry with the same filename already exists in `evidence_context.json`, `delete_evidence` is called first to fully clear the previous state (disk file, sibling `.summary.md`, context entry, session RAG index) before writing the new file. This makes re-uploads idempotent and prevents duplicate RAG chunks on retries. Previously a user who retried a failed upload got multiple vacuous entries stacked in `evidence_context.json` and duplicate chunks in the session RAG index.
- `llm_provider.stream_chat` now logs a `WARNING: stream_chat produced ZERO tokens — model=… provider=…` when the stream completes cleanly with no tokens yielded. Covers the silent-failure case where LM Studio responds but the model has been evicted from VRAM. Gives us a log signal to diagnose "why is the LLM not responding" without digging.
- Discovered via real conversation: Daniel uploaded 3 files; Gemma-vision processed the PNG (705 chars), the summariser processed a 1.2 MB PDF (2863 chars), but silently failed on a 110 KB PDF with `0 chars` summary. Daniel had to reload the summariser model in LM Studio manually. Root cause of the empty response was not conclusively identified (likely LM Studio model eviction) — captured for Sprint 17 resilience work (fallback cascade + admin notification + optional LM Studio CLI watchdog, see `docs/ideas.md`).
- Session folder naming (`sessions/{token}/` → readable `company-country-date-ordinal`) was considered and declined: Daniel will handle export/renaming via an external script. No code change.


- **Behaviour change — uploads no longer trigger an automatic LLM response.** The previous flow ("upload → backend immediately answers") was replaced by the Claude/ChatGPT mental model: attach files → chips appear in the input area → write the prompt around them → submit once. Files "ship with" the prompt and become evidence on the next user turn.
- **File-only send is allowed**: if the textarea is empty but at least one chip is `ready`, the file IS the user's response. The user message in history is synthesised as `[Attached: file1.pdf, photo.jpg]` so the conversation log stays readable and the model has a clear pivot point.
- **Claude-Style retraction**: each chip has an X button that deletes the file from disk, drops the entry from `evidence_context.json`, and rebuilds the session RAG so the file no longer influences future responses. Optimistic UI removal with backend confirmation via SSE.
- Backend `polling.py`: removed the call to `_respond_to_upload` and deleted the function entirely. `_safe_process` now reads `attachments: list[str]` from the queue body and synthesises the `[Attached: …]` user message when content is empty. INFO log when a turn ships with attachments. Image-evidence context injection fixed to differentiate analyzed images (full description text) from unanalyzed images.
- Backend `evidence_processor.py`: new `delete_evidence(token, filename)` with path-traversal guard, idempotent file removal, evidence_context cleanup, and session RAG rebuild. New `rebuild_session_index(token)` drops `_session_indices[token]` and re-builds the VectorStoreIndex from remaining files (text re-extracted, images use their sibling `.summary.md` if present).
- Backend `polling.py`: new `_handle_evidence_delete` helper drains `evidence_delete_requests` from the sidecar queue. Posts `evidence_deleting` SSE immediately, then `evidence_deleted` (success) or `evidence_delete_error` (failure). Busy check via `_processing_lock` returns `evidence_delete_error` with reason `"busy"` if a chat inference is in flight. Pull-inverse preserved.
- Sidecar `main.py`: new `DELETE /internal/evidence/{session_token}/{filename}` endpoint enqueues `{token, filename}` into `_evidence_delete_queue`. `GET /internal/queue` now includes `evidence_delete_requests` (drained on read, same pattern as `auth_requests`/`recovery_requests`). `SubmitMessageRequest` accepts optional `attachments: list[str]`.
- Frontend `ChatShell.tsx`: new `Attachment` type (`AttachmentStatus = 'uploading' | 'processing' | 'ready' | 'error'`). `attachments` state replaces the legacy `uploadStatus` banner. `processFiles` rewritten for parallel uploads with per-file chip lifecycle. Chip strip rendered above textarea — pill-shaped, icon, mid-truncated filename, status, X button. X disabled while `uploading`/`processing`. Send button gated by `canSend` (no in-flight chips, text OR ready chip exists). File-only send produces a user bubble showing the filenames. Send body extended with `attachments`. Chips cleared after send. Client-side filename collision via `reserveFilename` → `file (2).pdf`, `file (3).pdf`, etc.
- Frontend SSE handlers: `upload_received` removed (chip transitions on HTTP response, not on SSE). New `evidence_deleting`/`evidence_deleted`/`evidence_delete_error` handlers. `upload_processed` and `upload_error` now match by filename to update the right chip.
- i18n: 6 new keys across 31 languages (`attachment_uploading`, `attachment_processing`, `attachment_ready`, `attachment_error`, `attachment_remove`, `attachment_send_blocked`).
- Cleanup: `_respond_to_upload` removed entirely from `polling.py`. `upload_received` SSE event removed from both backend (emit) and frontend (handler). `uploadStatus` state removed from `ChatShell.tsx`. Orphaned i18n keys (`upload_analyzing`, `upload_doc_analyzed`, `upload_image_stored`, `upload_image_analyzed`, `upload_batch_progress`) left in place — declarative data, harmless, not worth 155 line churn across 31 languages.
- Architecture unchanged: still pull-inverse, frontends still independent, no new external dependencies.
- Backend + both frontworker and frontorganizer rebuilt.

### Sprint 15 — Multimodal images + internal-doc context guarantee (2026-04-11)
- **Block A — internal docs always see the full conversation**: added a module-level docstring to `polling.py` documenting the invariant that `_generate_document` (and therefore `session_summary_uni.md`, `internal_case_file.md`, and `summary.md`) always receives the full uncompressed conversation history. The compressor (`compress_if_needed`) is non-destructive — it returns a new list used only by chat inference and never mutates the session store. Added a token-budget safeguard: if the estimated message tokens exceed 90% of the slot's `num_ctx`, a WARNING is logged so the admin knows to raise `reporter_num_ctx`.
- **Block B — multimodal image analysis (opt-in)**: uploaded JPG/PNG can now be described by the inference LLM at upload time, with the resulting text injected into the case as evidence and indexed into the per-session RAG. Reuses the existing inference slot — no separate vision slot, no new model. Disabled by default behind a global `multimodal_enabled` toggle. Admin must select a vision-capable inference model (Gemma 3/4, Qwen2.5-VL, llava…). VRAM unchanged.
- Backend: `llm.py` adds `multimodal_enabled: false` to defaults + `LLMSettingsRequest`. `llm_provider.stream_chat` relaxes the `messages` content type to accept either plain strings or OpenAI multimodal content arrays (`{"type":"text",...}` + `{"type":"image_url","image_url":{"url":"data:..."}}`). Both LM Studio and Ollama accept this via `/v1/chat/completions`.
- Backend: new `evidence_processor.describe_image()` — base64-encodes the image, builds a multimodal message using the new `prompts/image_description.md` system prompt (factual, evidence-grade, transcribes visible text, no speculation), calls the inference slot, returns the description. 5MB hard cap on image size before base64. Failures fall back gracefully to "stored without analysis".
- Backend: `process_upload` IMAGE branch now calls `describe_image` when `multimodal_enabled` is on, saves `{filename}.summary.md`, indexes the description for session RAG, and stores it in `evidence_context.json`. Schema is backward-compatible — the `summary` field on image entries was already empty, now optionally populated.
- Backend: polling `upload_processed` SSE payload for images now includes the truncated summary so the frontend can switch wording.
- Admin UI: new toggle "Analyse uploaded images with the inference model" inside the existing **Inference** panel of `LLMTab.tsx`, with a hint right below the model selector reminding the admin to pick a vision-capable model when the toggle is on. Per-frontend LLM override is **not** extended for `multimodal_enabled` in this sprint — global only.
- Frontend: `ChatShell.tsx` upload_processed handler now reads `info.summary` for images; if non-empty it uses the new `upload_image_analyzed` i18n key and keeps the "Processing..." banner alive until the LLM responds (image is part of context now). Otherwise it falls back to the existing `upload_image_stored` wording.
- i18n: new `upload_image_analyzed` key in all 31 languages.
- Backend + both frontworker and frontorganizer rebuilt.

### Sprint 14 — Mobile chat UX + drag-and-drop (2026-04-11)
- **Mobile-friendly chat input**: restructured `ChatShell.tsx` input area from a single horizontal row into two rows. Row 1 is the textarea with the Send button embedded (icon-only, absolutely positioned bottom-right, 36×36 tap target). Row 2 has Attach (icon + translated label) on the left and End Session on the right, `justify-between`. On 360px mobile screens the textarea now gets the full width instead of ~120px.
- **Auto-expanding textarea**: removed fixed `rows={2}`; new `useEffect` resizes the textarea on every input change — sets `height='auto'` first to avoid the `scrollHeight` growth bug, then `height = min(scrollHeight, 50vh)`. Once content exceeds 50% of viewport height, the textarea switches to internal `overflow-y: auto` so the input bar never gets pushed off-screen. Min height ~3rem.
- **iOS auto-zoom fix**: textarea font size bumped from `text-sm` (14px) to `text-base` (16px) to stop Safari iOS from zooming the viewport when the keyboard opens.
- **iOS keyboard overlap fix**: main shell container switched from `h-[calc(100vh-64px)]` to `h-[calc(100svh-64px)]` (small viewport height) so the layout shrinks correctly when the virtual keyboard opens.
- **Drag & drop file upload**: users can now drag 1-4 files directly onto the input area (desktop only — mobile browsers don't support HTML5 drag events). Visual feedback: dashed blue border + light blue background + "Drop files here" overlay. Reuses the same `processFiles()` pipeline as the Attach button, so the 4-file limit, batch progress, and SSE upload events work identically. `dragCounter` ref prevents flicker from nested `dragenter`/`dragleave` events. Handlers attached to the input container only, so text selection in chat messages is unaffected.
- **i18n**: new `attach_file` and `drop_files_here` keys added to all 31 languages.
- **Tap targets**: Attach and End Session buttons get `min-h-[44px]` to meet Apple HIG minimum touch target.
- No backend changes. Both frontworker and frontorganizer rebuilt.

### Sprint 13 — Reporter LLM slot (2026-04-11)
- **Third LLM slot for internal documents**: new `reporter` slot dedicated to `session_summary_uni.md` (internal summary) and `internal_case_file.md` (report). Chat conversations continue using `inference`. Motivation: Gemma 4 is better for conversational flow, Qwen is better for structured analytical output — split lets each model play to its strengths.
- Backend: `llm.py` adds `reporter_*` defaults (provider, model, temperature `0.3`, max_tokens `4096`, num_ctx `32768`) and `use_reporter_for_user_summary` toggle (default `false`). `LLMSettingsRequest` extended with the new fields.
- Routing: `_generate_document()` gains a `slot` parameter. New `_slot_settings()` helper resolves per-slot provider/model/temperature/max_tokens/num_ctx with graceful fallback to inference when reporter fields are unset. `_generate_internal_documents()` always uses `slot="reporter"`. `_finalize_session()` respects the toggle for the user-facing summary. Auto-close (lifecycle) and admin manual regeneration (`sessions.py`) both honour the same routing.
- Admin UI: new "Reporter" panel in LLM tab below Inference — same structure (provider, model, temperature, max_tokens, context window) plus the toggle with helper text explaining the tradeoff. Per-Frontend LLM section now exposes both inference and reporter fields side by side, allowing each frontend to override either slot independently.
- Per-frontend override mechanism reused unchanged — merges reporter overrides on top of global settings automatically.
- No frontend (worker/organizer) rebuild needed — pure backend + admin change.

### Per-Frontend LLM Assignment (2026-03-15)
- **Per-frontend LLM override**: each registered frontend can now use a different inference provider/model instead of the global default
- Backend: `get_llm_settings(frontend_id)` loads per-frontend config from `/app/data/campaigns/{fid}/llm_settings.json`, falls back to global
- New API endpoints: `GET/PUT/DELETE /admin/frontends/{fid}/llm-settings`
- All LLM call sites updated: `polling.py` (chat, finalize, uploads), `session_lifecycle.py` (auto-close), `sessions.py` (admin doc generation)
- Admin LLM tab: new "Per-Frontend LLM" section with provider/model/temperature/max_tokens/context_window per frontend, reset-to-global option
- Bugfix: `_generate_internal_documents` now receives `frontend_id` (was missing, caused NameError in email notifications)

### Sprint 12 — UI Texts, Disclaimer Rewrite, Translation (2026-03-13)
- **Disclaimer page restructured**: 3 sections with headings (What Is This Tool, How Your Data Is Handled, Disclaimer), scrollable container, UNI logo centered at top
- **`data_protection_email` dynamic config**: configurable in deployment JSONs, served via sidecar `/internal/config`, replaces `[DATA_PROTECTION_EMAIL]` placeholder in disclaimer legal text at render time
- **Instruction texts rewritten by role**: worker (personal story, empathy, anonymity, "contact your local trade union"), representative (case-building, patterns, escalation, "share with your national union"), organizer (mode selection, framework context), officer (organizer + training paragraph)
- **Mode descriptions expanded**: longer descriptive texts for all 5 consultation modes (documentation, interview, advisory, submit evidence, training)
- **i18n.ts — complete 31-language coverage**: EN/ES/FR manually written with full new content; 13 existing languages (de, pt, ar, zh, hi, id, ja, ko, ru, tr, vi, th, sw) updated with all new keys + auth error messages translated; 15 new languages added (bn, mr, te, ta, ur, it, pl, nl, el, uk, ro, hr, xh, hu, sv) — 88+ keys per language, zero English fallbacks
- `BrandingConfig` type: added `custom` field for branding translation toggle
- `App.tsx`: `fetchBrandingText()` for per-language branding, `mergedBranding` combines base + translated text

### Sprint 11 — Polish, Copyright, Branding, Notifications (2026-03-12)
- **Copyright + Licensing**: `LICENSE` file (proprietary, UNI Global Union), copyright headers in key source files, visible footer "© 2026 UNI Global Union", package.json author/license fields
- **Navigation UX**: Back button on all pre-chat pages (Disclaimer, Session, RoleSelect, Auth, Instructions, Survey), `history.pushState` so browser back navigates to previous step, `beforeunload` handler warns on reload during chat/survey, amber warning box on Instructions page about not reloading
- **Multiple notification recipients**: `admin_notify_address` (single string) migrated to `notification_emails` (list), admin SMTP tab chip/tag UI for global recipients, per-frontend notification emails in `/app/data/campaigns/{fid}/notification_config.json`, admin SMTP tab per-frontend section, `notify_admin_report()` resolves frontend-specific + global recipients (deduplicates)
- **Per-frontend branding**: admin Frontends tab "Branding" button with editor (app title, logo URL, disclaimer text, instructions text), branding pushed to sidecar via `POST /internal/branding` (on save + during polling), sidecar serves branding in `/internal/config`, React pages use branding when available (header title, logo on language/disclaimer/instructions pages, disclaimer text, instructions text), UNI defaults when branding not configured
- i18n: `nav_back`, `instructions_no_reload` keys (EN/ES)

### Sprint 10 — Guardrails + Repetition Detection + Polish (2026-03-12)
- **Pre-LLM content filter** (`services/guardrails.py`): pattern-based detection of hate speech, discriminatory content, and prompt injection attempts
  - Fixed hardcoded response strings (NOT LLM-generated) in EN/ES/FR/DE/PT/IT, English fallback for others
  - Violation counter per session persisted in session.json
  - After 3 violations: session auto-flagged and ended gracefully
  - Respects `guardrails_enabled` and `guardrail_max_triggers` from deployment config
- **Model repetition detector** (`services/repetition_detector.py`): streaming analysis to detect and stop generation loops
  - Conservative thresholds: 25+ char phrases repeated 3+ times, only checks after 200+ chars
  - Stops streaming at repetition point, delivers clean partial response
  - Documented design principle: false positives worse than false negatives
- **Sprint 8h loose end**: auto-copy global prompts when registering new frontend in per_frontend mode
- `session_store.py`: `guardrail_violations` field in session metadata, `increment_guardrail_violations()` and `get_guardrail_violations()` methods
- Admin sessions list includes `guardrail_violations` count
- **UNI Global Union branding**: logo in header (inverted white), language selector (h-28), disclaimer/instructions (h-[7.5rem]), chat watermark (opacity 8%)
- **Block 4 — Code audit:**
  - SMTP config load: try-except for corrupt/empty JSON (was crash)
  - `poll_frontends()`: AsyncClient in try/finally (was resource leak on exception)
  - `_send_queue_positions()`: converted to `async with` (was resource leak)
  - All document writes (summary.md, report.md, internal_summary.md) now atomic (tmp+rename)
  - Prompt file reads wrapped in try-except with fallback
  - Context compressor: JSON response parsing with specific exception types
  - RAG service: silent `except: pass` replaced with logged warnings
  - Admin SMTP: parent dir creation, corrupt JSON handling
  - Removed dead `session_history.py` (replaced by session_store.py in Sprint 8a)
  - Removed unused `import time` from session_store.py

### Sprint 9 — SMTP + Email Auth + Guardrails Prompt + Production Prompts (2026-03-12)
- Full SMTP integration with aiosmtplib (auth codes, notifications, report/summary forwarding)
- Email authentication flow via pull-inverse (whitelist, 6-digit code, 10-min expiry, 3 attempts)
- Guardrails prompt layer (always injected between core and case prompt)
- 22 production prompt files (per-profile conversational, summaries, internal documents)
- Notification toggles in admin SMTP tab (notify on report, send summary/report to user)
- Authorized emails whitelist management in admin panel
- SMTP health check on startup (non-blocking)

### Sprint 8g-b — Batch Upload + UX Polish (2026-03-12)
- Multi-file upload: select up to 4 files at once (`<input multiple>`, client-side limit)
- Upload progress: "Uploading 1/3..." for batch uploads
- Processing indicator as assistant bubble with pulse animation (same style as message processing)
- "Processing document. This may take a minute — please don't leave the page." message
- Backend: uploads grouped by session token, single LLM response per batch
- `_respond_to_upload()` handles batch: references all documents, distinguishes text vs image
- `docx2txt` added to backend requirements (fixes .docx text extraction)
- Improved error message when text extraction fails
- i18n: `upload_analyzing`, `upload_batch_progress`, `upload_batch_limit` (EN/ES)

### Sprint 8g — Evidence Document Upload (2026-03-12)
- Evidence upload during chat sessions via pull-inverse architecture
- Sidecar: `POST /internal/upload/{token}` (temp storage), `GET/DELETE` for backend fetch+cleanup
- `services/evidence_processor.py`: text extraction, LLM summarisation, per-session RAG indexing
- Dual context injection: concise summaries as fixed system context + session-specific LlamaIndex for detail queries
- `prompts/evidence_summary.md`: dedicated summarisation prompt focused on labor rights relevance
- Polling integration: `_handle_upload()` fetches files, processes, sends SSE status events
- `ChatShell.tsx`: paperclip upload button, file picker with type filter, upload status indicator
- SSE events: `upload_received`, `upload_processed`, `upload_error` for real-time feedback
- Text files (.txt, .md, .pdf, .doc, .docx): summarised + indexed for session RAG
- Images (.jpg, .png): stored in evidence folder, model informed but no analysis
- Evidence persisted to `/app/data/sessions/{token}/evidence/` + `evidence_context.json`
- Nginx `client_max_body_size 26m` for upload support
- `python-multipart` added to sidecar requirements
- i18n: upload strings + disclaimer in instructions (EN/ES)
- Idea logged: image analysis as future enhancement (Backlog)

### Sprint 8f — Inactivity Timeout + Auto-Cleanup (2026-03-12)
- `services/session_lifecycle.py`: background scanner (every 5 min) for auto-closure and auto-cleanup
- Auto-closure: inactive sessions get documents generated (summary, internal_summary, report) then marked completed
- Auto-cleanup: old completed sessions archived from listing (files preserved on disk)
- Per-frontend lifecycle settings via admin Sessions tab ("Lifecycle Settings" button)
- Settings persisted to `/app/data/session_lifecycle.json`
- `session_store.py`: `archive_session()` method, archived sessions skipped on load
- `frontend_id` now stored in session metadata for lifecycle mapping
- Backend endpoints: `GET /admin/sessions/lifecycle`, `PUT /admin/sessions/lifecycle/{frontend_id}`

### Sprint 8e — Admin Session Enhancements (2026-03-11)
- Sessions table: document status indicators (✓/✗) for summary, internal summary, report
- Session detail: Documents section with view/collapse and markdown rendering
- On-demand document generation buttons (Generate / Regenerate) per document type
- Backend endpoints: `GET /admin/sessions/{token}/documents`, `POST /admin/sessions/{token}/generate/{doc_type}`
- Re-generation overwrites previous file on disk
- Works for any session (active or completed) — useful for abandoned sessions or prompt updates

### Sprint 8d — Report + Internal UNI Summary (2026-03-11)
- After session closure: background generation of internal UNI summary + structured report
- `session_summary_uni.md` prompt: severity, frameworks, integrity flag, priority for UNI staff
- `internal_case_file.md` prompt: formal case documentation with framework analysis
- Internal UNI summary saved as `{token}/internal_summary.md`
- Report saved as `{token}/report.md` (skipped for training mode sessions)
- Phase-based prompt loading: document prompts replace conversational system prompt
- Sequential generation after user-visible summary completes
- User does not see internal documents — background only

### Sprint 8c — End Session + Summary (2026-03-11)
- "End Session" button (red border) with confirmation dialog
- Per-profile summary prompts (`session_summary_{role}.md`) — 4 files, customizable per profile
- Summary streamed to chat as final assistant message, saved to disk + conversation history
- Session marked `completed`, chat input disabled after finalization
- Recovered completed sessions are read-only (no input, no End Session button)
- Markdown rendering with `react-markdown` + `remark-gfm` (GFM tables, strikethrough, task lists)
- Markdown applied in: chat messages, streaming, recovery context, admin session detail
- `@tailwindcss/typography` plugin for prose styling in both frontend and admin
- Smart auto-scroll: pauses when user scrolls up during streaming
- Admin Sessions table: company column, frontend origin column, horizontal scroll
- Admin Frontends: inline editable frontend names
- Frontend origin stored in session metadata on first message
- `session_summary_uni.md` replaces generic `session_summary.md` (for 8d internal use)
- i18n: 6 new keys (EN/ES) for end session flow
- Fix: summary now saved as conversation message (visible on recovery)
- Fix: recovered completed sessions blocked from sending messages

### Sprint 8b — Session Recovery (2026-03-11)
- Session recovery via pull-inverse: sidecar queues request → backend resolves from disk → pushes data back
- Hybrid recovery: compression summary for long conversations, full messages for short ones
- Compression summaries now persisted to `{token}/compression_summary.json`
- Sidecar: 3 new endpoints for recovery flow (request, poll, push data)
- Frontend: "Recovering..." loading state, error handling (expired/not found/timeout)
- ChatShell: recovered sessions show previous context (summary or messages) with "Session resumed" separator
- Recovery skips role select, instructions, survey — goes straight to chat
- 120h max resume window enforced backend-side

### Sprint 8a — Session Persistence to Disk (2026-03-11)
- `services/session_store.py`: disk-backed store with in-memory cache, replaces session_history.py
- `session.json` per session: survey, language, role, mode, timestamps, status, flagged
- `conversation.jsonl`: one JSON line per message with timestamps, appended in real-time
- Atomic writes (tmp + rename) for session.json
- Sessions survive backend restart (loaded from disk on startup)
- Flag toggle persists to disk
- Admin sessions tab: status badges (active/completed/flagged), 4 filter buttons, timestamps, last activity

### Sprint 7c — User Flow Redesign + Monolithic Prompts (2026-03-11)
- New user flow: language → disclaimer → session → **role selection** → auth (if required) → **instructions** → survey → chat
- `RoleSelectPage.tsx`: Profile selection with 2 cards per frontend type (worker/rep or organizer/officer)
- `InstructionsPage.tsx`: Hardcoded per-profile instructions before survey
- `SurveyPage.tsx`: Role from previous phase, mode selector only for organizer/officer with descriptions
- Mode options: Organizer (document, interview, advisory, submit), Officer (+training)
- Company field required for all profiles except advisory/training modes
- Privacy note for worker/rep: anonymous allowed, contact recommended
- Monolithic case prompts replace modular core+role+mode concatenation:
  - Worker/Rep: single prompt each (`worker.md`, `worker_representative.md`)
  - Organizer/Officer: per-case prompts (`organizer_document.md`, `officer_training.md`, etc.)
- 9 new prompt files (functional placeholders for Daniel to customize)
- `prompt_assembler.py`: `_resolve_case_prompt()` maps role+mode to file, logs loaded prompt
- Admin Prompts tab updated with new categories (Worker Profiles, Organizer Cases, Officer Cases)
- i18n: ~25 new keys (role selection, instructions, mode descriptions) in EN and ES
- Other languages use English fallback; translation sprint planned later

### Sprint 7b — Context Compression (2026-03-10)
- `services/context_compressor.py`: Incremental compression with running summary per session
- `prompts/context_compression.md`: Dedicated compression prompt preserving names, dates, facts, case data
- Token estimation before every LLM call (logged: token count + message count)
- Two-phase compression: incremental summary updates + injection when inference hits threshold
- Configurable threshold via admin panel slider (50-90% of context window)
- Direct HTTP calls to summariser (avoids stream conflicts with inference)
- `<think>` block stripping for Qwen3 summariser responses
- Admin LLM tab redesigned:
  - Context Window field visible for all providers (not just Ollama)
  - Provider-specific hints (Ollama override vs LM Studio manual match)
  - Compression Threshold slider with calculated trigger point display
  - Removed summariser max_tokens from UI (internal detail)
- Fix: model selector auto-corrects when switching provider (was keeping old provider's model name)
- ADR-009: Documented decision to use simple compression over Letta (Sprint 12 for future swap)
- `/git` command: generates commit + push to GitHub and Gitea

### Sprint 7a — RAG with LlamaIndex (2026-03-10)
- `services/rag_service.py`: LlamaIndex vector index with sentence-transformers embeddings
- Embedding model: `all-MiniLM-L6-v2` (80MB, CPU-only, auto-downloaded from HuggingFace)
- Documents indexed from `/app/data/documents/`, index persisted to `/app/data/rag_index/`
- RAG chunks injected per-message as system context before the user's latest message
- Admin Reindex button now triggers real re-indexing (was stub)
- Index loads from disk on container restart — no re-embedding needed
- Lazy initialization: embedding model only loaded when first needed
- Dependencies: `llama-index-core`, `llama-index-readers-file`, `llama-index-embeddings-huggingface`, `sentence-transformers`

### Sprint 6b — Knowledge Base + Documentation (2026-03-10)
- Knowledge base: `glossary.json` (15 domain terms, 6 languages) + `organizations.json` (14 entries)
- Backend endpoints: `/admin/knowledge/glossary`, `/admin/knowledge/organizations` (GET/PUT)
- Prompt assembler: glossary + organizations injected as layer 5 in every session context
- Admin RAG tab: Glossary editor (add/edit/delete terms with translations) + Organizations Directory editor
- Default knowledge files installed on first startup, atomic writes
- Spec §13: Added guardrails (§13.1), session integrity (§13.2), internal UNI assessment (§13.3), phase-based prompt loading (§13.4)
- Milestones: Sprint 8 updated with internal assessment, new Sprint 10 for guardrails
- `docs/knowledge/prompt-assembly-flow.md`: Complete prompt architecture documentation
- `docs/INSTALL.md`: Installation and usage guide

### Sprint 6 — Admin Panel Complete (2026-03-10)
- **Prompts tab**: two-column editor with 5 categories (System, User, Use Cases, Context, Post-Processing), save with dirty tracking
- **RAG tab**: upload documents (.md/.txt/.json, 10MB limit), list with size/date, delete, reindex stub
- **Sessions tab**: list all sessions with All/Flagged filters, view conversation detail, flag/unflag toggle
- **SMTP tab**: full config form (host, port, username, password, from address, admin notify, TLS toggle), test connection stub
- Backend: 4 new router modules (`prompts.py`, `sessions.py`, `rag.py`, `smtp.py`) with 13 endpoints
- SMTP config persists to `/app/data/smtp_config.json` with atomic writes
- RAG documents stored in `/app/data/documents/` (indexing deferred to Sprint 7)
- Fix: survey `type` field now always sent from frontend (was conditional on role, causing "unknown" mode for worker/representative sessions)
- Fix: session mode default changed from "unknown" to "documentation"
- Added `python-multipart` dependency for file upload support

### Sprint 5b — LLM Tab Improvements (2026-03-09)
- Split LLM admin tab into Inference and Context Compression (Letta) subpanels
- Toggle to enable/disable Letta summariser
- Context window (num_ctx) field for Ollama on both panels
- Hints with recommended values and page equivalents for all parameters
- Fix: health refresh no longer overwrites unsaved settings edits
- Discard Changes and Reset to Defaults buttons

### Sprint 5 — LLM Integration (2026-03-09)
- `services/llm_provider.py`: LM Studio + Ollama via OpenAI-compatible API, streaming + non-streaming
- `services/prompt_assembler.py`: Modular prompt assembly (core + role + mode + survey context)
- `services/session_history.py`: In-memory conversation history per session token
- 11 default prompt files: core.md, worker.md, worker_representative.md, organizer.md, officer.md, documentation.md, advisory.md, training.md, context_template.md, session_summary.md, internal_case_file.md
- Auto-install defaults to `/app/data/prompts/` on first startup (won't overwrite edits)
- `api/v1/admin/llm.py`: Health check, model listing, settings CRUD
- Admin LLM tab: provider status (green/red), model dropdowns, temperature slider, max_tokens, num_ctx
- LLM settings persist to `/app/data/llm_settings.json`
- `<think>` block filtering: Qwen3 reasoning tokens stripped from user-visible response
- Mock LLM fallback when no provider is available
- Health checks wrapped in try-except (lesson #3)
- All background processing wrapped in try-except with error push to stream (lesson #2)

### Sprint 4 — Message Queue + Polling (2026-03-09)
- Full pull-inverse pipeline: React → sidecar queue → backend poll → mock LLM → SSE stream → React
- Frontend sidecar: `POST /internal/queue`, `GET /internal/queue`, `POST /internal/stream/{token}/chunk`, `GET /internal/stream/{token}` (SSE)
- Backend polling loop with sequential processing (one message at a time for LLM constraint)
- Queue position feedback via SSE (`queue_position` event)
- Frontend registry: persistent JSON with atomic writes (lesson #5), auto-discovery via `/internal/config`
- Admin Frontends tab: register by URL, enable/disable, remove, status indicators (green/red/gray), auto-refresh
- `ChatShell.tsx`: real chat with EventSource streaming, user bubbles right/blue, assistant left/white
- EventSource error handling: UI unblocks after 3 consecutive failures (lesson #1)
- Message TTL: 300s expiry in sidecar queue
- 31 languages supported (15 new with English fallback via `Partial<Record>` pattern)
- Survey fields: all visible on both frontends, required varies by frontend type

### Sprint 3 — Frontend User Flow (2026-03-09)
- Complete phase state machine: loading → language → disclaimer → session → auth? → survey → chat
- 16 languages with full UI translations (EN, ES, FR, DE, PT, AR, ZH, HI, ID, JA, KO, RU, TR, VI, TH, SW)
- LanguageSelector: responsive 4-column grid with native language names
- DisclaimerPage: translated purpose statement per language
- SessionPage: WORD-NUMBER token generation (24 nature words + 4-digit random)
- AuthPage: email verification flow (mock, SMTP in Sprint 9)
- SurveyPage: role-dependent fields matching §3.4 matrix exactly
- ChatShell: placeholder with session token display
- Frontend sidecar: `/internal/config` endpoint reads deployment JSON
- Organizer frontend shows auth step, worker skips it
- Footer with disclaimer, hidden during chat phase

### Sprint 2 — Backend Core: Admin Auth + Config (2026-03-09)
- `src/backend/core/config.py`: Pydantic config loader for `deployment_backend.json`
- `src/backend/api/v1/admin/auth.py`: Admin setup, login, JWT auth (HS256, bcrypt)
- Admin React app (`src/admin/`): SetupPage, LoginPage, Dashboard with UNI colors
- First-run flow: "Create Admin Account" → bcrypt hash → `/app/data/.admin_hash`
- JWT: 24h default expiry, 30d with "remember me", verify endpoint
- Backend Dockerfile: multi-stage (Node build for admin SPA + Python runtime)
- Backend serves admin SPA at `/` root via FastAPI catch-all route

### Sprint 1 — Project Scaffolding (2026-03-09)
- `Dockerfile.backend`: Python 3.11-slim + FastAPI + uvicorn
- `Dockerfile.frontend`: Multi-stage (Node 20 build → Python 3.11-slim runtime with Nginx + supervisord)
- 3 Docker Compose files: backend (8000), frontworker (8091), frontorganizer (8090)
- Backend: FastAPI skeleton with `/health` endpoint
- Frontend: React 18 + Vite 6 + Tailwind 3.4 with UNI color palette
- Frontend sidecar: FastAPI skeleton with `/internal/health`
- Nginx config: SSE streaming headers, SPA fallback, sidecar proxy
- supervisord manages Nginx + sidecar in frontend container
- All containers verified: build, run, health checks, /app/data volumes

### Sprint 0 — Project Setup (2026-03-09)
- Created product specification (SPEC-v2.md)
- Set up project structure for Claude Code
- Created GitHub repo: https://github.com/DFergo/LAIUNI

---

## v1.x — Previous Version (archived)

### Sprint 11f-fix
- Removed PreChatPage component
- Fixed nginx SSE buffering
- Added debug logging
- Fixed placeholder IP

### Sprint 11f
- Removed frontend_id shared secret
- Simplified frontend registration (auto-generated IDs)
- Introduced chat regression (not resolved)

### Sprint 11e
- Removed frontend admin panel
- Split compose per frontend type
- Standardized ports (8090 organizer, 8091 worker)

### Sprint 11d
- Admin cleanup
- Hostname-based frontend auto-discovery

### Sprint 11b+11c
- Admin UI improvements
- Session finalization (summary + report)
- Docker split (separate Dockerfiles for backend and frontend)

### Sprint 11b
- Multi-step user flow (language → disclaimer → session → auth → survey → chat)
- Markdown chat rendering

### Sprint 11a ✓ (Last working version)
- Prompt loading architecture
- Survey integration
- Chat flow working end-to-end

### Sprint 10a
- LLM provider abstraction (LM Studio + Ollama)
- Production deployment configs

### Sprint 9
- Security layer (injection detection, guardrails, rate limiting)

### Sprint 8
- Admin Panel (prompts, RAG, frontends, sessions, LLM, SMTP tabs)
