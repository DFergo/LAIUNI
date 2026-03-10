# Prompt Assembly Flow — How Survey, Prompts, and Knowledge Work Together

This document describes how the different components combine to form the LLM context in each session. Use it as a reference when writing or reviewing prompts.

---

## 1. Session Initialization

When a user completes the survey and sends their first message, the backend assembles the system prompt from modular files. The order matters — each layer adds specificity.

```
User completes survey → first message sent
                            ↓
        Backend: assemble_system_prompt(survey, language)
                            ↓
        ┌─────────────────────────────────────┐
        │           SYSTEM PROMPT             │
        │                                     │
        │  1. Core prompt (core.md)           │
        │  2. User prompt ({role}.md)         │
        │  3. Use case prompt ({mode}.md)     │
        │  4. Context (survey data rendered)  │
        │  5. Knowledge base (glossary + orgs)│
        └─────────────────────────────────────┘
                            ↓
        LLM receives: [system prompt] + [user message]
```

---

## 2. The Five Layers

### Layer 1: Core Prompt (`core.md`)

**Loaded:** Every session, always.
**Purpose:** Identity, non-negotiable constraints, scope, language rules.

This is the foundation. It defines:
- Who the AI is (UNI G&P HRDD Helper)
- What it cannot do (legal advice, direct escalation, fabricate citations)
- What frameworks it operates under (ILO, OECD, FSC, UNGP, CSDDD)
- How to handle cases outside scope (honestly, without dismissing the user)
- Language behavior (use session language, don't switch unless asked)
- How to reference the knowledge base

**Key principle:** The core prompt never changes between sessions. It's the same for a worker in Indonesia and an officer in Germany.

### Layer 2: User Prompt (`{role}.md`)

**Loaded:** One per session, selected by the `role` field from the survey.
**Files:** `worker.md`, `worker_representative.md`, `organizer.md`, `officer.md`

Each role prompt adjusts:
- **Tone:** warm and accessible for workers → direct and collegial for officers
- **Assumed knowledge:** explain everything for workers → skip basics for officers
- **Priorities:** emotional safety for workers → strategic analysis for officers
- **Session integrity:** awareness of possible imposters (especially in worker sessions)

**Important:** The user prompt defines *how* to talk to the person, not *what* to talk about. The "what" comes from the use case prompt.

### Layer 3: Use Case Prompt (`{mode}.md`)

**Loaded:** One per session, selected by the `type` field from the survey.
**Files:** `documentation.md`, `advisory.md`, `training.md`

| Mode | Purpose | Behavior |
|------|---------|----------|
| **Documentation** | Document a specific violation | Structured interview: who, what, when, where, evidence. Guide toward complete case file. |
| **Advisory** | Analyze a situation | Strategic assessment: which frameworks apply, what leverage exists, what to recommend. |
| **Training** | Learn about frameworks | Educational: explain concepts, provide examples, answer questions about standards. |

**Worker frontend:** Always `documentation` (hardcoded, user has no choice).
**Organizer frontend:** User selects from all three modes.

### Layer 4: Context Template (`context_template.md`)

**Loaded:** Every session where survey data exists.
**Purpose:** Injects the survey answers into the prompt so the AI knows who it's talking to and about what.

The template uses placeholders that get replaced with survey data:

```
{role}           → worker / representative / organizer / officer
{mode}           → documentation / advisory / training
{name}           → User's name (or "Not provided")
{position}       → User's position
{union}          → User's union
{email}          → User's email
{company}        → Company involved
{country_region} → Country or region
{language}       → Session language code
{description}    → The situation description from the survey
```

This gives the AI immediate context without the user needing to repeat their situation in the chat.

### Layer 5: Knowledge Base (glossary + organizations)

**Loaded:** Every session, automatically.
**Source:** `glossary.json` and `organizations.json` from `/app/data/knowledge/`

Unlike RAG documents (which are indexed and retrieved based on relevance), the knowledge base is injected **in full** into every session context. This guarantees:

- **Term consistency:** The AI uses the exact translations from the glossary, not improvised translations. If "Freedom of Association" is in the glossary with its Spanish translation "Libertad sindical", the AI will use that term, not a paraphrase.
- **Organization accuracy:** The AI only recommends organizations from the curated list. It cannot invent unions, federations, or contact details. The escalation path is always worker → national union → UNI.

**Glossary injection** filters translations to the session language for conciseness:
```
- **Freedom of Association** (Libertad sindical): The right of workers to form and join organizations... [ILO Convention 87, ILO Convention 98]
```

**Organizations injection** includes all entries with their descriptions and notes:
```
- **UNI Global Union** (UNI) — Global Union Federation representing over 20 million workers...
- **ILO** — International Labour Organization... *Note: Do not recommend direct contact.*
```

---

## 3. Conversation Flow

After initialization, the conversation follows this pattern:

```
Turn 1:
  System: [assembled system prompt — all 5 layers]
  User:   [survey description, auto-sent as first message]
  AI:     [initial response]

Turn 2+:
  System: [same system prompt — unchanged]
  User:   [new user message]
  AI:     [response using full conversation history]
```

The system prompt stays fixed throughout the conversation. What grows is the conversation history (user + assistant messages appended after each exchange).

**Context window pressure:** As conversations get long, the total context (system prompt + history) approaches the LLM's limit. This is where Letta/MemGPT comes in (Sprint 7) — it compresses older conversation turns while preserving key information.

---

## 4. RAG Context (Sprint 7)

When RAG is active, relevant document chunks are retrieved based on the user's message and injected into the prompt:

```
System prompt (5 layers) + RAG context + conversation history + user message
```

RAG provides specific passages from uploaded documents (ILO conventions, OECD guidelines, etc.) that are relevant to the current question. Unlike the knowledge base, RAG is dynamic — different chunks are retrieved for different messages.

---

## 5. Session Closure — Phase-Based Prompt Swap

At session closure, the prompt architecture changes completely. The conversational prompt is **replaced**, not extended:

### Summary Generation
```
System: [session_summary.md prompt]  ← replaces all 5 layers
User:   [full conversation transcript]
AI:     [structured summary]
```

### Report Generation
```
System: [internal_case_file.md prompt]  ← different prompt
User:   [full conversation transcript + survey data]
AI:     [structured report with framework analysis]
```

### Internal UNI Assessment
```
System: [internal_assessment prompt]  ← English only
User:   [full conversation transcript + survey data]
AI:     [honest severity assessment + integrity flag]
```

**Why swap instead of stack?** Loading the conversational prompt alongside the report prompt would waste context and introduce conflicting instructions (e.g., "be warm and supportive" vs "be analytically objective"). Each phase gets a clean, focused prompt.

---

## 6. What the Admin Controls

| Component | Admin edits via | Effect |
|-----------|----------------|--------|
| Core prompt | Prompts tab → `core.md` | Changes AI identity and constraints for ALL sessions |
| User prompts | Prompts tab → `worker.md`, etc. | Changes tone and behavior per role |
| Use case prompts | Prompts tab → `documentation.md`, etc. | Changes behavior per mode |
| Context template | Prompts tab → `context_template.md` | Changes what survey data the AI sees |
| Glossary | RAG tab → Glossary section | Changes term definitions and translations |
| Organizations | RAG tab → Organizations Directory | Changes which organizations the AI can reference |
| RAG documents | RAG tab → upload/delete | Changes what reference material is available |
| Summary/report prompts | Prompts tab → `session_summary.md`, etc. | Changes how closure documents are generated |

---

## 7. Checklist for Prompt Review

When reviewing or writing prompts, verify:

- [ ] **Core prompt** does not reference any specific role, mode, or use case (those come from other layers)
- [ ] **User prompts** define tone and behavior, not content scope (that comes from use case prompts)
- [ ] **Use case prompts** define what to do and how to structure the conversation, not how to speak to the user (that comes from user prompts)
- [ ] **Context template** has all required placeholders and handles "Not provided" gracefully
- [ ] **Glossary** covers all critical terms in all supported languages
- [ ] **Organizations** directory has accurate contact info and correct escalation notes
- [ ] **Summary/report prompts** work without the conversational prompt (they replace it, not extend it)
- [ ] No layer contradicts another layer
- [ ] Session integrity instructions are in user prompts (not in use case prompts)
- [ ] The AI is told to reference the knowledge base in the core prompt
