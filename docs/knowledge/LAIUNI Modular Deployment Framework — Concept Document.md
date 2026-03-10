# LAIUNI Modular Deployment Framework — Concept Document

**Status:** Idea / Pre-design  
**Date:** February 2026  
**Author:** Daniel Fernandez / UNI Global Union

-----

## 1. Vision

LAIUNI’s core architecture (FastAPI backend + React frontend + local LLM) is generic and reusable. What changes between deployments are the “modules”: the portal interface, the system prompts, the document library, and the configuration parameters.

The idea is to wrap this architecture in a **management app** (desktop GUI or local web panel) that allows anyone to deploy and configure a LAIUNI instance without touching the terminal. This would make it easier to:

- Adapt LAIUNI to new use cases beyond HRDD Helper and Staff Tool
- Hand off deployments to non-technical administrators
- Standardize configurations across multiple instances
- Reduce deployment time and error risk

### Core design principle: phase-based prompt loading

The system’s prompt context changes according to the **phase of the interaction**, not just the user profile. Loading everything into context from the start would waste the context window and introduce noise. Instead:

- During conversation: only the active conversational mode prompt is loaded
- At report generation: the conversational prompt is replaced by the report prompt, the full conversation is passed as input, and the report is generated in a single dedicated call
- This keeps each LLM call focused and avoids overloading the context window with instructions that are irrelevant to the current phase

-----

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────┐
│             LAIUNI Manager (App/GUI)             │
│  ┌──────────┬──────────┬────────┬─────────────┐  │
│  │  Config  │  Prompts │  RAG   │  Knowledge  │  │
│  └──────────┴──────────┴────────┴─────────────┘  │
└──────────────────┬──────────────────────────────┘
                   │ writes config files
         ┌─────────▼──────────┐
         │   LAIUNI Core      │
         │  FastAPI + React   │
         │  + LLM (local)     │
         └────────────────────┘
```

The Manager app reads and writes a `deployment.json` profile file. The LAIUNI Core picks up configuration from that file at startup (or on reload). No code changes required between deployments — only profile files change.

-----

## 3. Configuration Module

Settings that control how the LAIUNI instance connects and behaves at the infrastructure level.

### 3.1 Network

|Parameter           |Description                                 |Example                              |
|--------------------|--------------------------------------------|-------------------------------------|
|`backend_host`      |IP address or hostname of the backend server|`192.168.1.50`                       |
|`backend_port`      |Port where FastAPI listens                  |`8000`                               |
|`frontend_host`     |IP or DNS of the frontend server            |`hrdd.uniglobalunion.org`            |
|`frontend_port`     |Port for the React dev server or nginx      |`3000` / `443`                       |
|`backend_dns`       |Optional domain name for the backend        |`backend.laiuni.local`               |
|`use_https`         |Enable HTTPS (requires cert paths)          |`true` / `false`                     |
|`ssl_cert_path`     |Path to SSL certificate                     |`/etc/letsencrypt/live/...`          |
|`ssl_key_path`      |Path to SSL private key                     |`/etc/letsencrypt/live/...`          |
|`tailscale_enabled` |Use Tailscale VPN instead of direct network |`true` / `false`                     |
|`tailscale_hostname`|Tailscale hostname for backend              |`loveland-m4.tailabca8d.ts.net`      |
|`allowed_origins`   |CORS whitelist                              |`["https://hrdd.uniglobalunion.org"]`|

### 3.2 LLM Engine

|Parameter             |Description                             |Example                              |
|----------------------|----------------------------------------|-------------------------------------|
|`llm_provider`        |LLM serving backend                     |`lmstudio` / `ollama` / `api`        |
|`llm_host`            |Host where LLM server runs              |`localhost`                          |
|`llm_port`            |Port for LLM API                        |`1234` (LM Studio) / `11434` (Ollama)|
|`model_name`          |Active model identifier                 |`deepseek-r1-distill-llama-70b`      |
|`model_context_window`|Context window in tokens                |`8192` / `128000`                    |
|`request_timeout`     |Max wait time for LLM response (seconds)|`120`                                |
|`max_tokens_response` |Maximum tokens in a single response     |`2048`                               |
|`temperature`         |Model temperature                       |`0.3`                                |
|`streaming_enabled`   |Enable token streaming to frontend      |`true` / `false`                     |

### 3.3 Sessions & Concurrency

|Parameter                     |Description                                             |Example           |
|------------------------------|--------------------------------------------------------|------------------|
|`session_storage_path`        |Where session data is stored                            |`./data/sessions/`|
|`max_concurrent_sessions`     |Active sessions allowed simultaneously                  |`5`               |
|`session_queue_enabled`       |Queue users when limit reached                          |`true` / `false`  |
|`session_queue_max`           |Max users waiting in queue                              |`20`              |
|`session_timeout_minutes`     |Inactivity timeout before session expires               |`60`              |
|`session_max_duration_minutes`|Hard cap on session length                              |`180`             |
|`max_messages_per_session`    |Message limit per session                               |`50`              |
|`session_resumable`           |Allow users to resume interrupted sessions              |`true` / `false`  |
|`session_resume_window_hours` |How long a session remains resumable after last activity|`24`              |
|`session_resume_method`       |How users identify their session to resume it           |`token` / `email` |
|`session_resume_token_display`|Show resumption token/link to user at session start     |`true` / `false`  |

**Session resumption** allows users to continue interrupted or paused sessions using a token displayed prominently at the start of every session. Behaviour differs by frontend type:

- **Worker frontend**: token is the only resumption method. Window is 48 hours. After expiry, session is locked and a new one must be started.
- **Organizer frontend**: token or dashboard selection. Window is 6 days for active resumption. Older sessions remain visible for reference and report download but cannot be continued.

In both cases, when a user returns within the window the full conversation history is reloaded and the session continues exactly where it left off. If a report has already been generated, the user is shown the output screen rather than the chat interface.

The session token is a short, human-readable code (not a full UUID) displayed immediately after the disclaimer, with an explicit instruction to save it. Format is configurable — e.g. `WOLF-4821` — short enough to write down.

### 3.4 File Uploads

|Parameter             |Description                    |Example                          |
|----------------------|-------------------------------|---------------------------------|
|`uploads_enabled`     |Allow users to upload documents|`true` / `false`                 |
|`upload_max_size_mb`  |Max file size per upload       |`20`                             |
|`upload_allowed_types`|Accepted file formats          |`["pdf", "docx", "txt"]`         |
|`uploads_path`        |Storage path for uploads       |`./data/sessions/{uuid}/uploads/`|

### 3.5 Security & Access

|Parameter                       |Description                       |Example                            |
|--------------------------------|----------------------------------|-----------------------------------|
|`registration_required`         |Require registration before access|`true` / `false`                   |
|`registration_fields`           |Fields collected at registration  |`["name", "email", "organization"]`|
|`admin_password`                |Password for the Manager interface|`[hashed]`                         |
|`rate_limit_requests_per_minute`|API rate limiting                 |`10`                               |
|`log_conversations`             |Store conversation logs           |`true` / `false`                   |
|`log_retention_days`            |How long to keep logs             |`90`                               |

-----

## 4. System Prompt Module

The system prompt is split into **layers** loaded according to the current phase of the interaction. This avoids overloading the context window with instructions that are irrelevant at a given moment.

### 4.1 Prompt Architecture by Phase

**Phase 1 — Conversation (active session)**

```
active_prompt = core_prompt + mode_module + context_module
```

**Phase 2 — Report generation (end of session)**

```
report_call_prompt = report_prompt + full_conversation_transcript
```

The report is generated in a **dedicated LLM call** — separate from the conversation. The conversational prompt is not present. The report prompt receives the full conversation as input and produces the structured output. This call is triggered either automatically (when the system detects sufficient information) or manually (when the user signals they are done).

### 4.2 Prompt Layers

**Layer 1 — Core Identity (rarely changes)**  
Defines who the AI is, its fundamental behavior, tone, and non-negotiable constraints. Shared across all sessions regardless of mode.

```
You are LAIUNI, a specialized AI assistant for [ORGANIZATION].
Your responses must be professional, accurate, and grounded in the documents provided.
You never speculate beyond your knowledge base. You acknowledge uncertainty explicitly.
[...base constraints...]
```

**Layer 2 — Conversational Mode Module (selected per session)**  
Defines the objective and conversational style for this specific session. One of three pre-built modes, or a custom one. This is what changes the character of the interaction fundamentally.

*Mode: Formación (Learning)*  
The user wants to understand international standards — ILO conventions, OECD guidelines, FSC, CSDDD — without a specific case in mind. The system explains concepts accessibly, contextualizes them practically, and guides exploration. No case documentation. Tone: educational, patient, approachable.

*Mode: Consulta (Advisory)*  
The user is a union organizer or worker with a real case. The system helps apply international standards to the specific situation, supports strategy, and advises on next steps. Documentation of the case happens as a byproduct of the conversation, not as a primary objective. Tone: supportive, collegial, practical.

*Mode: Denuncia (Documentation)*  
The user needs to formally document a labor rights violation. The system proactively extracts structured information through empathetic conversation: what happened, when, who was involved, what standards apply. Documentation is the primary objective. Tone: empathetic, methodical, reassuring. The system is aware that users in this mode may be in a vulnerable position.

**Layer 3 — Context Module (injected dynamically from survey)**  
Populated automatically from the onboarding survey. Includes user profile, target company, country, sector, and campaign context.

```
The user is a [worker / union organizer / researcher / affiliate staff].
The target company is [Company Name], operating in [Country], in the [Industry] sector.
The user's primary language is [language].
Relevant campaign context: [free text from survey].
```

**Layer 4 — Report Prompt (loaded only at report generation)**  
Used exclusively in the dedicated report generation call. Not present during conversation. Instructions for how to structure the output document: what sections to include, what language to use, how to cite standards, what level of detail is expected.

The report prompt is separate from the conversational mode — the same Denuncia conversation could generate different report formats depending on the report prompt loaded (e.g., internal case file vs. formal complaint to a regulatory body vs. campaign briefing document).

### 4.3 Mode Selection

Mode is selected during onboarding, either by the user explicitly (“I want to learn about FSC standards” / “I have a case I need help with” / “I need to file a complaint”) or via a guided question in the survey. The selected mode is stored in `metadata.json` and determines which mode module is loaded for the session.

Mode can be changed during the session by the user (e.g., “actually, I want to document this formally”). When mode changes, the new module is loaded and the conversation continues — the history is preserved.

### 4.4 Manager Interface for Prompts

- **Core Prompt editor**: Locked by default, requires admin confirmation to edit. Version history with rollback.
- **Mode Module editor**: One tab per mode (Formación / Consulta / Denuncia). Each editable independently. New custom modes can be added.
- **Context Module**: Read-only preview showing how the template populates from a sample survey response. Editable template with `{{variables}}`.
- **Report Prompt editor**: Separate editor. Supports multiple report templates (e.g., “Internal case file”, “Formal complaint”, “Campaign brief”). Each template is a separate file.
- **Preview**: Assemble and display the full prompt for any combination of mode + context before saving.
- **Test**: Send a test query with the assembled prompt to the connected LLM. Show raw response.
- **Version history**: Last N versions of each layer, per-layer rollback.

-----

## 5. Frontend / Portal Module

Configuration for the user-facing interface.

### 5.1 Branding

|Parameter          |Description                         |
|-------------------|------------------------------------|
|`portal_name`      |Name shown in browser tab and header|
|`organization_name`|Displayed organization name         |
|`logo_path`        |Path to logo image file             |
|`primary_color`    |Brand color (hex)                   |
|`secondary_color`  |Accent color (hex)                  |
|`favicon_path`     |Browser favicon                     |

### 5.2 Layout & Flow

|Parameter                  |Description                                  |Options                                        |
|---------------------------|---------------------------------------------|-----------------------------------------------|
|`onboarding_flow`          |Steps shown before chat                      |`language → survey → chat` (configurable order)|
|`survey_enabled`           |Show registration/profile survey             |`true` / `false`                               |
|`survey_profile`           |Which survey to load                         |`hrdd_helper` / `staff_tool` / `custom`        |
|`language_selector_enabled`|Show language picker at start                |`true` / `false`                               |
|`default_language`         |Fallback language                            |`en`                                           |
|`supported_languages`      |Languages available to users                 |Array of language codes                        |
|`chat_input_placeholder`   |Placeholder text in chat box                 |Per language                                   |
|`show_sources`             |Display RAG document sources in responses    |`true` / `false`                               |
|`streaming_ui`             |Show streaming text vs wait for full response|`true` / `false`                               |

### 5.3 Queue & Capacity UX

|Parameter                  |Description                            |
|---------------------------|---------------------------------------|
|`queue_message`            |Text shown to users waiting in queue   |
|`queue_show_position`      |Show position number in queue          |
|`queue_show_estimated_wait`|Show estimated wait time               |
|`busy_message`             |Text shown when system is fully busy   |
|`maintenance_mode`         |Take portal offline with custom message|
|`maintenance_message`      |Message shown during maintenance       |

### 5.4 Translations

All UI strings are managed in a `translations.json` file (the existing `translations.js` in LAIUNI is the right foundation). The Manager app exposes:

- List of all UI strings with their keys
- Per-language text editor
- Status indicator showing which languages have complete coverage
- Import/export translations as JSON
- Machine translation assist (send string to LLM for draft translation, human reviews)

-----

## 6. RAG Documents Module

Manages the document library used for Retrieval-Augmented Generation.

### 6.1 Document Library

The Manager app provides a simple interface to:

- **Upload documents**: PDF, DOCX, TXT. Stored in `./data/rag/documents/`
- **Tag documents**: Assign category tags (e.g., `ILO`, `OECD`, `CSDDD`, `FSC`, `internal`)
- **Set visibility**: Which document categories are loaded for this deployment
- **View index status**: Whether each document has been indexed into the vector store
- **Re-index**: Trigger re-indexing of specific documents or the full library
- **Delete**: Remove documents from the library and vector store

### 6.2 Index Management

|Parameter             |Description                                      |
|----------------------|-------------------------------------------------|
|`vector_store_path`   |Where the vector index is persisted              |
|`embedding_model`     |Model used to generate embeddings                |
|`chunk_size`          |Token size per document chunk                    |
|`chunk_overlap`       |Overlap between chunks                           |
|`top_k_results`       |Number of chunks retrieved per query             |
|`similarity_threshold`|Minimum similarity score to include a result     |
|`persist_index`       |Save index to disk (avoid re-indexing on restart)|

### 6.3 Document Categories (HRDD Helper defaults)

Pre-built categories matching the HRDD Helper use case:

- ILO Core Conventions (87, 98, 29, 105, 100, 111, 138, 182)
- ILO Fundamental Principles
- OECD Guidelines for Multinational Enterprises
- EU CSDDD (Corporate Sustainability Due Diligence Directive)
- FSC Standards (if applicable)
- UNGP (UN Guiding Principles on Business and Human Rights)
- Internal / Organization-specific documents

### 6.4 Document Status Panel

A simple table view showing:

```
Document Name          | Category | Size   | Indexed | Last Updated
-----------------------|----------|--------|---------|-------------
ILO_Convention_87.pdf  | ILO      | 1.2MB  | ✅ Yes  | 2025-01-10
OECD_Guidelines.pdf    | OECD     | 3.8MB  | ✅ Yes  | 2025-03-22
CSDDD_EU_2024.pdf      | CSDDD    | 890KB  | ⚠️ Pending | —
internal_policy.docx   | Internal | 145KB  | ✅ Yes  | 2026-01-05
```

-----

## 7. Report & Output Module

When the conversation has gathered sufficient information — detected automatically or triggered manually by the user — the system initiates a dedicated report generation call.

### 7.1 Report Generation Flow

```
1. Trigger (automatic or user-initiated)
2. Backend assembles: report_prompt + full conversation transcript
3. Single LLM call — conversational prompt not present
4. LLM generates structured report
5. Backend saves report to configured output path
6. Frontend notifies user: report ready, download link shown
7. Session marked as complete
```

The trigger logic can be configured: the system can look for a minimum number of exchanges, detect when key information fields are populated, or simply wait for the user to say they’re done. In Denuncia mode this is more proactive; in Consulta mode more passive.

### 7.2 Report Templates

Multiple report formats can be configured, each with its own prompt. Examples for the HRDD Helper:

- **Internal case file**: Structured summary for UNI/affiliate internal use. Includes timeline, parties, violations identified, standards cited, recommended next steps.
- **Formal complaint**: Formatted for submission to a regulatory body or certification scheme (e.g., FSC complaints procedure). More formal language, precise standard citations.
- **Campaign briefing**: Shorter, designed for communications use. Focuses on key findings and narrative.
- **Session summary** (Formación mode): Recap of topics covered, key concepts, resources cited.

The report template used is configured per deployment profile, but can also be selected per session if multiple templates are available.

### 7.3 Output Configuration

|Parameter                  |Description                                   |Example                          |
|---------------------------|----------------------------------------------|---------------------------------|
|`report_output_path`       |Where generated reports are saved             |`./data/sessions/{uuid}/reports/`|
|`report_filename_pattern`  |Naming convention for report files            |`{date}_{company}_{mode}_report` |
|`report_formats`           |Output formats to generate                    |`["pdf", "md", "docx"]`          |
|`report_include_transcript`|Append full conversation transcript to report |`true` / `false`                 |
|`report_include_sources`   |List RAG documents cited during session       |`true` / `false`                 |
|`report_notify_admin`      |Alert admin when a new report is generated    |`true` / `false`                 |
|`report_notify_email`      |Admin email for notifications                 |`hrdd@uniglobalunion.org`        |
|`report_auto_trigger`      |Automatically trigger report when session ends|`true` / `false`                 |
|`report_user_downloadable` |Allow user to download report from portal     |`true` / `false`                 |
|`report_retention_days`    |How long reports are kept on disk             |`365`                            |
|`report_default_template`  |Which template to use if not specified        |`internal_case_file`             |

### 7.4 Report Prompt Management (in Manager)

- List of available report templates, each with its own prompt file
- Editor per template — separate from the conversational prompts
- Test: paste a sample conversation transcript, generate a draft report, review output
- Templates are stored as `.md` files in `./prompts/reports/`

-----

## 8. Knowledge Base Module

Structured, curated data that the system uses deterministically — not through RAG or LLM interpretation, but through direct lookup. This guarantees accuracy for sensitive information like organizational referrals.

### 8.1 Glossary

A curated dictionary of terms used in the domain. When a user asks about a term, or when the system uses a term that may need explanation, it looks it up here first rather than relying on the LLM’s general knowledge.

Structure: `glossary.json`

```json
{
  "terms": [
    {
      "term": "Freedom of Association",
      "short_definition": "The right of workers to form and join organizations of their choosing.",
      "long_definition": "...",
      "related_standards": ["ILO Convention 87", "ILO Convention 98"],
      "languages": {
        "es": "Libertad sindical",
        "fr": "Liberté syndicale"
      }
    }
  ]
}
```

The Manager app provides a glossary editor: add/edit/delete terms, manage translations per term, import/export as JSON or CSV.

### 8.2 Organization Directory

A curated list of organizations that the system may recommend to users, maintained by UNI administrators. The LLM **does not decide** which organizations to recommend — it retrieves from this list based on structured lookup (country + sector + organization type) and presents the result. This prevents the model from recommending organizations that UNI has not vetted or that may be politically problematic.

Structure: `organizations.json`

```json
{
  "organizations": [
    {
      "id": "uni-europa",
      "name": "UNI Europa",
      "type": "ETUF",
      "scope": "regional",
      "region": "Europe",
      "countries": ["all-EU"],
      "sectors": ["all-UNI"],
      "description": "European regional organization of UNI Global Union.",
      "contact_url": "https://www.uni-europa.org",
      "contact_email": "..."
    },
    {
      "id": "industriall-global",
      "name": "IndustriALL Global Union",
      "type": "GUF",
      "scope": "global",
      "sectors": ["manufacturing", "mining", "energy", "textile"],
      "description": "Global union federation covering manufacturing, energy, and mining sectors.",
      "contact_url": "https://www.industriall-union.org"
    }
  ]
}
```

Lookup logic (backend, not LLM):

```
user country + user sector → filter organizations by country match + sector match → return ordered list
```

The Manager app provides a directory editor: add/edit/delete organizations, filter by type/region/sector, import/export as JSON or CSV.

### 8.3 Knowledge Base in Manager

- **Glossary tab**: Term list with search, inline editor, translation status per language
- **Directory tab**: Organization list with filters, inline editor, add/remove
- **Import/Export**: Both glossary and directory exportable as JSON for backup or sharing between deployments
- **Validation**: Check for missing translations in active languages, duplicate terms, broken URLs

-----

## 9. Ethical Guardrails and Content Boundaries

This section applies to all LAIUNI deployments. It is especially critical for any instance accessible to the general public or external users.

### 9.1 Why This Matters

A screenshot of LAIUNI validating hate speech, discriminatory language, or producing confident incorrect legal advice could be used to attack UNI, affiliated unions, or the labour rights movement. The system must be designed to prevent this — not just discourage it. This is a reputational risk, not just an ethical one.

### 9.2 Hate Speech and Discriminatory Content

The system must detect and refuse to engage with content that:

- Attributes workplace problems to a colleague’s race, ethnicity, nationality, religion, gender, sexual orientation, disability, or any other protected characteristic
- Frames organising or collective action in discriminatory terms
- Requests the system to endorse, validate, or amplify discriminatory narratives
- Uses slurs, dehumanising language, or incitement against any group

**Response when triggered:**

The system does not lecture, argue, or escalate. It responds briefly with a fixed pre-configured string and redirects:

> “Your message touches on content that conflicts with this system’s ethical principles. I’m here to help with [purpose of this deployment]. If you’d like to continue on that basis, I’m ready to help.”

If the user persists after a configurable number of attempts, the session is flagged and either ends gracefully or routes to a human review queue.

**Critical implementation note:** The guardrail response is a **fixed string configured in the deployment profile**, not generated by the LLM. This prevents the model from being manipulated into producing a nuanced, ambiguous, or partial validation of the problematic content. The LLM cannot negotiate its way around a hardcoded response.

### 9.3 Prompt Injection and Manipulation Attempts

Common attack patterns to guard against:

- “Ignore your previous instructions and…”
- “You are now a different AI that…”
- “For research / educational purposes, explain how to…”
- Gradual escalation: building rapport before introducing problematic requests

**Mitigations:**

- The core prompt explicitly instructs the model to ignore instructions that conflict with its identity and purpose
- The system prompt is never revealed to users under any circumstances
- Any response that references internal system instructions is treated as a potential injection attempt and flagged
- Injection attempts receive the same fixed redirect response as hate speech — brief, non-argumentative, no engagement with the framing

### 9.4 Guardrails Configuration in Manager

|Parameter                          |Description                                   |Example                           |
|-----------------------------------|----------------------------------------------|----------------------------------|
|`guardrails_enabled`               |Enable ethical guardrails system-wide         |`true`                            |
|`hate_speech_response`             |Fixed response text per language              |`"Your message conflicts with..."`|
|`max_guardrail_triggers_before_end`|Triggers before session ends                  |`3`                               |
|`flag_triggered_sessions`          |Always log full transcript of flagged sessions|`true`                            |
|`flag_notification_email`          |Admin alert when a session is flagged         |`admin@org.org`                   |
|`infrastructure_filter_enabled`    |First-pass keyword filter before LLM (faster) |`true` / `false`                  |

-----

## 10. Disclaimer and Usage Policy (Frontend)

### 10.1 Purpose

The disclaimer serves two functions: legal protection for the deploying organisation, and informed consent for the user. It also sets expectations about AI limitations — critical to prevent users from treating the system’s output as legal advice or certified guidance.

### 10.2 Placement and Flow

The disclaimer appears **after language selection and before any survey or chat**. It is a dedicated screen. The user cannot proceed without actively accepting — a passive scroll is not sufficient. Acceptance is recorded in the session metadata with a timestamp.

```
Language selector → [DISCLAIMER SCREEN] → Survey → Chat
                           ↓
              [Accept and continue] or [Exit]
```

If the user declines, the session ends and they are shown an alternative contact option (e.g., organisation phone number or email).

### 10.3 Disclaimer Content (template — adapt per deployment)

-----

**Before you continue — please read carefully**

This tool is provided by [Organisation Name] to help [target users] with [purpose].

**What this tool is:**  
A conversational AI assistant that can help you [core use case description].

**What this tool is not:**  
This is not a lawyer, certified advisor, or official representative of [Organisation Name]. The information it provides is for guidance only and may contain errors or inaccuracies. Do not make decisions based solely on what this tool tells you. For serious legal or labour matters, seek qualified professional advice.

**Your data:**  
Information you share in this conversation may be used to [data use description]. You will be asked explicitly before any of your personal details are shared with third parties. You can request deletion of your data at any time by contacting [contact].

**Acceptable use:**  
This tool is designed for [intended purpose] only. Content that is hateful, discriminatory, or abusive will not be processed and may result in your session being ended.

**By continuing, you confirm that you have read and accept these terms.**

[ Accept and continue ]   [ Exit ]

-----

### 10.4 Disclaimer Configuration in Manager

|Parameter                              |Description                                         |
|---------------------------------------|----------------------------------------------------|
|`disclaimer_enabled`                   |Whether disclaimer screen is shown                  |
|`disclaimer_content`                   |Text content per language (Markdown)                |
|`disclaimer_requires_active_acceptance`|Require button click (not just scroll)              |
|`disclaimer_acceptance_logged`         |Record acceptance with timestamp in session metadata|
|`disclaimer_decline_redirect_url`      |Where to send users who decline                     |
|`disclaimer_decline_message`           |Message shown to users who decline                  |

-----

## 11. Deployment Profiles

A **profile** bundles all configuration into a single portable file. This is what makes the framework reusable across different deployments.

### 9.1 Profile File Structure (`deployment.json`)

```json
{
  "profile_name": "HRDD Helper - Production",
  "profile_version": "1.2",
  "created": "2026-02-19",
  "network": { "..." },
  "llm": { "..." },
  "sessions": {
    "session_resumable": true,
    "session_resume_window_hours": 24,
    "session_resume_method": "token"
  },
  "security": { "..." },
  "prompts": {
    "core": "prompts/core.md",
    "modes": {
      "formacion": "prompts/modes/formacion.md",
      "consulta": "prompts/modes/consulta.md",
      "denuncia": "prompts/modes/denuncia.md"
    },
    "context_template": "prompts/context_template.md",
    "default_mode": "consulta"
  },
  "reports": {
    "templates": {
      "internal_case_file": "prompts/reports/internal_case_file.md",
      "formal_complaint": "prompts/reports/formal_complaint.md",
      "campaign_brief": "prompts/reports/campaign_brief.md"
    },
    "default_template": "internal_case_file",
    "output_path": "./data/sessions/{uuid}/reports/",
    "formats": ["pdf", "md"],
    "user_downloadable": true
  },
  "frontend": { "..." },
  "rag": {
    "document_categories": ["ILO", "OECD", "CSDDD"],
    "index_config": { "..." }
  },
  "knowledge": {
    "glossary": "knowledge/glossary.json",
    "organizations": "knowledge/organizations.json"
  }
}
```

### 9.2 Profile Management in Manager

- **Load profile**: Select a `.json` file to configure the entire instance
- **Save profile**: Export current configuration as a `.json` file
- **Profile templates**: Built-in starting points (HRDD Helper, Staff Tool, Generic)
- **Apply changes**: Restart affected services (backend reload, frontend rebuild if needed)
- **Profile diff**: Compare two profiles side by side to see what changed

-----

## 12. Dual Frontend Architecture

### 12.1 The Problem It Solves

Two distinct user populations need access to the system with fundamentally different experiences:

- **Workers**: arrive via specific links or QR codes, often anonymously, in a vulnerable position. They should never be able to identify themselves as union members or organizers. Mode and profile are predefined — the worker makes no configuration choices.
- **Organizers and union staff**: need access to the full system, can select mode and user profile, may want persistent sessions across multiple days, and require accountability via login.

The solution is two separate frontends pointing to a single shared backend. The underlying mechanism for loading modular instructions is identical in both — what differs is who controls the choices.

### 12.2 Architecture

```
workers.union.org       →  Frontend Worker   (mode + profile predefined in deployment profile)
                      ↘
                         Backend (FastAPI)  →  LLM  →  Shared RAG
                      ↗
organizers.union.org    →  Frontend Organizer (mode + profile selectable, login required)
```

The backend distinguishes sessions via `session_type: worker | organizer` in session metadata. This controls which options are available and which modular instructions are loaded. No other architectural difference — one backend, one LLM, one RAG index.

**Why not two separate backends?**

The risk vector that matters is a worker accessing the organizer frontend. That is resolved by authentication — a worker without credentials simply cannot log in. The reverse (an organizer finding the worker URL) is not a problem: the worker frontend has fewer capabilities, not more sensitive ones. Two backends would double infrastructure complexity and maintenance without adding meaningful security benefit.

### 12.3 User Flow — Both Frontends

The flow is linear in both cases. There is no session dashboard or history interface. The token is the only mechanism for session recovery.

```
Portal landing page
    ↓
Language selection
    ↓
Information page + Disclaimer  ← (CAPTCHA here if configured)
    ↓
[Organizer frontend only: Login — email + password]
    ↓
Survey screen:
  ┌─────────────────────────────────────────┐
  │  Do you have a session number?          │
  │                                         │
  │  [ Enter session number ] → Resume      │
  │                                         │
  │  [ Start a new session ]                │
  └─────────────────────────────────────────┘
    ↓                          ↓
Chat resumes where          New session survey
it was left off             (profile, company, etc.)
                                ↓
                            Chat opens with
                            initial welcome message
```

If a token is entered but has expired or is not found, the user is told clearly and offered to start a new session instead.

### 12.4 Frontend Worker

- No login, no account creation
- Mode and user profile are **hardcoded in the deployment profile** — the worker makes no configuration choices
- Accessed via specific URL, QR code, or short link — not publicised as a general-access portal
- Session token is displayed prominently at the top of the chat at session start, with an explicit instruction: *“Save this number — you will need it if you get disconnected or want to continue later.”*
- Token format: short human-readable code (e.g. `WOLF-4821`), not a UUID — short enough to write down
- Resume window: **48 hours** from last activity

**Output at session end:**  
A **one-page summary** designed to be useful to the worker: key issues discussed, relevant rights, recommended next steps, contact details for the relevant union office. Downloadable as PDF. The full structured report is generated separately for internal union use and is never shown to the worker.

### 12.5 Frontend Organizer

- Login required: email + password (see §12.6 for authentication details)
- After login, the flow continues identically to the worker frontend: survey screen with token or new session
- Resuming by token requires that the session belongs to the logged-in user — a token from another user’s session will not work
- Resume window: **6 days** from last activity
- Full mode and profile selection available in the new session survey
- All three conversational modes available (Learning / Advisory / Documentation)

**Output at session end:**  
Two outputs available:

- **Full report**: structured case file, violations identified, standards cited, recommended actions. Defined by the report prompt template.
- **Conversation summary**: condensed one-page narrative, useful for briefing colleagues or attaching to a campaign file.

Both downloadable as PDF. Full report also saved as structured JSON for potential CRM integration.

### 12.6 Session Flow Comparison

|                         |Worker Frontend               |Organizer Frontend                    |
|-------------------------|------------------------------|--------------------------------------|
|Access                   |Anonymous                     |Email + password login                |
|Token display            |Prominent, at chat start      |Prominent, at chat start              |
|Resume window            |48 hours                      |6 days                                |
|Resume method            |Token only                    |Token only (must match logged-in user)|
|Token expiry behaviour   |Inform user, offer new session|Inform user, offer new session        |
|Output at end            |One-page worker summary (PDF) |Full report + summary (PDF + JSON)    |
|Mode selection           |Predefined, no choice         |User selects at new session survey    |
|Session history interface|None                          |None                                  |

### 12.7 Authentication System (Organizer Frontend)

At 100–200 users, a simple admin-managed system is sufficient. No OAuth, no external identity provider needed.

**User record structure:**

```json
{
  "user_id": "uuid",
  "email": "organizer@union.org",
  "name": "Anna Schmidt",
  "role": "organizer",
  "active": true,
  "created_at": "2026-02-19T...",
  "last_login": "2026-02-19T...",
  "token_limit_daily": 50000,
  "token_limit_monthly": 500000,
  "token_used_today": 12400,
  "token_used_month": 87200,
  "token_limit_override": null,
  "sessions": ["uuid1", "uuid2", "..."]
}
```

**Authentication flow:**

1. User enters email + password
2. Backend validates against hashed password in users database (SQLite, same instance as sessions)
3. Backend issues a signed JWT with configurable expiry
4. Frontend stores JWT, includes in all API requests
5. On expiry, user is prompted to log in again

**Password management:**

- Admin creates accounts and sets initial passwords via Manager panel
- User can change their own password after first login
- Password reset: admin resets manually, or via email if SMTP is configured
- Passwords stored as bcrypt hashes, never in plaintext

**Admin capabilities in Manager:**

- Add / deactivate users (no hard delete — deactivation preserves session history)
- Reset passwords
- View token usage per user
- Adjust individual token limits or set override (unlimited) for specific users
- View any user’s session list and open any session for review

### 12.8 Token Usage Tracking and Limits

Token counting happens at the backend level, per API call to the LLM. Usage is logged in the user record and checked before each request.

|Parameter                      |Description                                    |Example           |
|-------------------------------|-----------------------------------------------|------------------|
|`token_tracking_enabled`       |Track token usage per user                     |`true`            |
|`token_limit_daily_default`    |Default daily cap for all organizer accounts   |`50000`           |
|`token_limit_monthly_default`  |Default monthly cap                            |`500000`          |
|`token_limit_action`           |What happens when limit is reached             |`warn` / `block`  |
|`token_warn_threshold`         |Warn user when X% of limit is used             |`80`              |
|`token_reset_schedule`         |When daily/monthly counters reset              |`daily: 00:00 UTC`|
|`worker_sessions_token_tracked`|Also track tokens for anonymous worker sessions|`true` / `false`  |

When a limit is reached with `block` action, the user sees a clear message explaining the situation and who to contact for a limit increase. Sessions in progress are not cut off mid-response — the block applies to new requests only.

### 12.9 Deployment Profile Configuration

Two deployment profiles are maintained — one per frontend — both pointing to the same backend.

`deployment_worker.json`:

```json
{
  "frontend_url": "workers.union.org",
  "session_type": "worker",
  "auth_required": false,
  "mode_locked": "documentation",
  "profile_locked": "worker",
  "session_resumable": true,
  "session_resume_window_hours": 48,
  "session_token_prominent_display": true,
  "output_worker_summary": true,
  "output_full_report": false,
  "disclaimer_enabled": true
}
```

`deployment_organizer.json`:

```json
{
  "frontend_url": "organizers.union.org",
  "session_type": "organizer",
  "auth_required": true,
  "mode_selectable": true,
  "profile_selectable": true,
  "session_resumable": true,
  "session_resume_window_hours": 144,
  "token_tracking_enabled": true,
  "output_worker_summary": true,
  "output_full_report": true,
  "output_conversation_summary": true,
  "disclaimer_enabled": true
}
```

-----

## 13. Manager App — Implementation Options

Two viable approaches, in order of implementation complexity:

**Option A — Local web panel (simpler, faster)**  
A `/admin` route in FastAPI serving a React admin interface. Accessible at `http://localhost:8000/admin`. Password protected. No extra installation required.

**Option B — Electron desktop app (more polished)**  
A standalone macOS/Windows app. Better for non-technical users, looks professional, can include system tray icon showing server status. More effort to build and maintain.

**Recommendation:** Start with Option A during active development. Migrate to Option B when the system is stable and if the framework is genuinely being adapted for external deployments.

-----

## 15. What This Is Not

To keep scope realistic:

- **Not a multi-tenant SaaS**: Each instance is a single deployment on dedicated hardware. The Manager manages one instance at a time.
- **Not automatic model management**: Selecting a model assumes it’s already downloaded in LM Studio / Ollama. The Manager doesn’t download models.
- **Not a deployment pipeline**: It configures and starts services. CI/CD, SSH, or rsync-based deployment remains separate.
- **Not built yet**: This is a concept document. The core LAIUNI architecture should be fully stable before building the Manager layer.

-----

## 16. Next Steps (When Ready)

1. Finalize and stabilize LAIUNI core (Sprints 4–7)
2. Define which configuration parameters are actually touched between deployments (empirical, based on real usage)
3. Implement `deployment.json` schema and loader in FastAPI
4. Build `/admin` panel as Option A
5. Evaluate if Electron wrapper adds enough value for Option B

-----

*This document captures an architectural concept for future development. Priority remains on the LAIUNI core system.*