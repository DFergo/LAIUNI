# Campaign Deployment — Customizing Prompts & Modules

How to turn the vanilla, industry-agnostic install into a deployment tailored to a specific company or campaign (e.g. a Tetra Pak deployment). Everything here is **per-frontend configuration** — the vanilla defaults are never edited.

## The customization surface

A campaign deployment is one **frontend** whose behaviour you tune in five places, all from the admin panel:

1. **Per-frontend prompts** — a private copy of the prompt set for this frontend, including a **Company Profile** in its `core.md` (see below). Admin → *Prompts* (switch to per-frontend / copy from global, then edit).
2. **Feature modules** — enable framework modules (e.g. **FSC**) globally or for this frontend. Admin → *RAG* → *Feature Modules* (global) and the per-campaign override in each frontend's panel.
3. **Per-campaign RAG** — upload company-specific documents (company profile, sector law, GFA text). Admin → *RAG* → *Campaign Documents*. You can also toggle "Include Global RAG" per frontend.
4. **Knowledge** — glossary / organizations directory, if the campaign needs specific terminology or contacts.
5. **Frontend config** — profiles (roles), auth per profile, display names, modes, languages, branding.

## Step-by-step: a company deployment

1. **Register the frontend** and give it a name.
2. **Company Profile in `core.md`.** Switch prompts to per-frontend (copy from global), then add a `## Company Profile` section near the top of this frontend's `core.md`, right after Identity. State the fixed, given facts and include the corporate-structure safeguard note (see next section). This is always-on, so the model treats these as established and does not re-ask them.
3. **Enable the module(s).** Turn on the relevant feature module (e.g. FSC) for this frontend. That injects the module's framework into the reference list, its intake question(s), and its report section — and its documents into RAG — only for this deployment.
4. **Upload campaign RAG.** Add the fuller company-profile document, the applicable national due-diligence law, GFA text, etc. Decide whether to keep the global RAG included.
5. **Configure profiles/modes/languages/branding** in the frontend config panel.
6. **Verify** a session per active role: the profile facts are treated as given (not asked), the module framework appears in the report, and the campaign RAG is retrieved.

## The Company Profile section (what to put in `core.md`)

Include whatever is **fixed and useful to treat as established**:

- Company (the investigation subject) and, if relevant, the ultimate parent / group.
- Sector, headquarters, approximate worldwide employee count, approximate annual revenue.
- Presence in countries with mandatory human-rights due-diligence laws (EU CSDDD scope, Germany's LkSG, France's *devoir de vigilance*, Norway's Transparency Act).
- Certification status (e.g. FSC-certified) and any Global Framework Agreement (GFA).
- Major buyers / customers, where relevant to leverage.

Always include the **corporate-structure safeguard**, so a worker who is not actually employed by the subject is handled correctly:

> The subject of this deployment is **[Company]**. If the user actually works for a different entity (a subsidiary, a supplier in the chain, or the parent), record their real employer and its relationship to [Company] — do not assume they work for [Company].

## How the pieces compose

- **Modules re-inject their content through slots** in the vanilla prompts (`{{module_frameworks}}`, `{{module_intake}}`, `{{module_report_sections}}`). You do not edit those slots — enabling the module fills them. So a module contributes, only when active: its framework (reference), its intake question (e.g. "is the company FSC-certified?", asked only for organizer/officer/representative — never workers), and its report section.
- **The profile makes facts *given*.** Because the module's intake question is phrased "unless already known from the context", a profile that states the company is certified means the model will not ask.
- **Do not duplicate.** Whatever the module already injects (framework, certification question, report section) should not be re-added by hand to the per-frontend prompts.

## Reference

- Prompt-assembly order: `core (incl. Company Profile) → guardrails → case prompt → survey context → knowledge → RAG (global + campaign + active modules)`.
- The vanilla default RAG set and the module documents ship with the app; the per-campaign RAG is what you add per deployment.
