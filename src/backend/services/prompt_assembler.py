"""Assembles the system prompt from case-specific prompt files + survey context + knowledge base.

Sprint 7c: Monolithic case prompts replace modular core+role+mode concatenation.
Sprint 8h: Per-frontend prompt sets (exclusive model — toggle Global / Per Frontend).
Structure: core.md + case prompt (per profile+case) + context_template + knowledge base.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.core.paths import PROMPTS_DIR, CAMPAIGNS_DIR

logger = logging.getLogger("backend.prompts")

# Default prompts shipped with the app — copied to data dir on first run
_DEFAULTS_DIR = Path(__file__).parent.parent / "prompts"


def _global_prompts_dir() -> Path:
    """Always return the global prompts directory (for admin, defaults, etc.)."""
    return PROMPTS_DIR


def _frontend_prompts_dir(frontend_id: str) -> Path:
    return CAMPAIGNS_DIR / frontend_id / "prompts"


# --- Per-frontend Global/Custom flag (Sprint 32) ---
# Replaces the single global prompt-mode switch. Each frontend either serves the
# GLOBAL prompt set (use_global=True) or its own custom copies (False). Custom
# copies are never deleted when re-coupling — they simply stop being applied.

def _prompts_flag_path(frontend_id: str) -> Path:
    return CAMPAIGNS_DIR / frontend_id / "prompts_config.json"


def get_use_global(frontend_id: str) -> bool:
    """Whether a frontend serves the GLOBAL prompt set (True) or its own custom
    copies (False). Default when unset: derive from current state — a frontend
    that already has custom prompt files is treated as decoupled (custom)."""
    p = _prompts_flag_path(frontend_id)
    if p.exists():
        try:
            return bool(json.loads(p.read_text()).get("use_global", True))
        except Exception:
            pass
    return not frontend_has_custom_prompts(frontend_id)


def set_use_global(frontend_id: str, use_global: bool) -> bool:
    """Set the Global/Custom flag for a frontend (does not touch custom files)."""
    p = _prompts_flag_path(frontend_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"use_global": bool(use_global)}))
    logger.info(f"Prompt source for {frontend_id}: {'global' if use_global else 'custom'}")
    return bool(use_global)


def frontend_has_custom_prompts(frontend_id: str) -> bool:
    """Check if a frontend has any custom prompt files."""
    campaign_dir = CAMPAIGNS_DIR / frontend_id / "prompts"
    return campaign_dir.exists() and any(campaign_dir.glob("*.md"))


def reset_prompt_to_default(name: str, frontend_id: str | None = None) -> str:
    """Reset a single prompt to its default; return the new content.

    Per-frontend: restore that frontend's copy from the current GLOBAL prompt.
    Global: restore the global prompt from the bundled FACTORY default.
    """
    if not name.endswith(".md") or "/" in name or "\\" in name:
        raise ValueError("Invalid prompt name")
    if frontend_id:
        src = _global_prompts_dir() / name
        dst_dir = CAMPAIGNS_DIR / frontend_id / "prompts"
    else:
        src = _DEFAULTS_DIR / name
        dst_dir = _global_prompts_dir()
    if not src.exists():
        raise FileNotFoundError(f"No default available for prompt: {name}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    content = src.read_text()
    (dst_dir / name).write_text(content)
    logger.info(f"Reset prompt {name} to default (frontend={frontend_id or 'global'})")
    return content


def reset_frontend_prompt_to_factory(name: str, frontend_id: str) -> str:
    """Overwrite a frontend's custom copy of a prompt from the FACTORY default.

    Distinct from reset_prompt_to_default(name, frontend_id), which restores the
    frontend copy from the current GLOBAL prompt (Sprint 32: two reset sources).
    """
    if not name.endswith(".md") or "/" in name or "\\" in name:
        raise ValueError("Invalid prompt name")
    src = _DEFAULTS_DIR / name
    if not src.exists():
        raise FileNotFoundError(f"No factory default for prompt: {name}")
    dst_dir = _frontend_prompts_dir(frontend_id)
    dst_dir.mkdir(parents=True, exist_ok=True)
    content = src.read_text()
    (dst_dir / name).write_text(content)
    logger.info(f"Reset frontend {frontend_id} prompt {name} to factory")
    return content


def ensure_defaults():
    """Copy default prompt files to data dir if they don't exist yet."""
    dest = _global_prompts_dir()
    dest.mkdir(parents=True, exist_ok=True)
    for src_file in _DEFAULTS_DIR.glob("*.md"):
        dst_file = dest / src_file.name
        if not dst_file.exists():
            dst_file.write_text(src_file.read_text())
            logger.info(f"Installed default prompt: {src_file.name}")


def _load(name: str, frontend_id: str | None = None) -> str:
    """Load a prompt file by name. Returns empty string if not found.

    Per-frontend (Sprint 32): a decoupled frontend (use_global=False) serves its
    own custom copy of a prompt when present, otherwise falls back to the global
    file. A coupled frontend always serves the global file.
    Applies feature-module slot substitution ({{module_*}}); no-op when absent.
    """
    path = None
    if frontend_id and not get_use_global(frontend_id):
        cand = _frontend_prompts_dir(frontend_id) / name
        if cand.exists():
            path = cand
    if path is None:
        path = _global_prompts_dir() / name
    if path.exists():
        from src.services.modules import apply_slots
        return apply_slots(path.read_text().strip(), frontend_id)
    logger.warning(f"Prompt file not found: {name}")
    return ""


def _resolve_case_prompt(role: str, mode: str) -> str:
    """Resolve the case prompt file name for a given role+mode combination.

    Worker and Representative: single prompt (worker.md, worker_representative.md)
    Organizer and Officer: per-case prompt (organizer_document.md, officer_training.md, etc.)

    Maps consultation modes to file names:
      documentation -> {role}_document.md
      interview -> {role}_interview.md
      advisory -> {role}_advisory.md
      submit -> {role}_submit.md
      training -> {role}_training.md (officer only)
    """
    if role == "worker":
        return "worker.md"
    if role == "representative":
        return "worker_representative.md"

    # Organizer and Officer: per-case prompts
    mode_to_file = {
        "documentation": "document",
        "interview": "interview",
        "advisory": "advisory",
        "submit": "submit",
        "training": "training",
    }
    file_suffix = mode_to_file.get(mode, "document")
    return f"{role}_{file_suffix}.md"


def _render_context(survey: dict[str, Any] | None, language: str, frontend_id: str | None = None) -> str:
    """Render context_template.md with survey data."""
    template = _load("context_template.md", frontend_id)
    if not template or not survey:
        return ""

    replacements = {
        "{role}": survey.get("role", "unknown"),
        "{mode}": survey.get("type", "documentation"),
        "{name}": survey.get("name", "Not provided"),
        "{position}": survey.get("position", "Not provided"),
        "{union}": survey.get("union", "Not provided"),
        "{email}": survey.get("email", "Not provided"),
        "{company}": survey.get("company", "Not provided"),
        "{country_region}": survey.get("countryRegion", "Not provided"),
        "{language}": language,
        "{description}": survey.get("description", ""),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def _build_knowledge_section(survey: dict[str, Any] | None, language: str) -> str:
    """Build knowledge base section from glossary and organizations JSONs.

    These are structured, curated data injected directly into context.
    The LLM uses them for deterministic term lookups and organization referrals.
    """
    from src.api.v1.admin.knowledge import load_glossary, load_organizations

    parts: list[str] = []

    # Glossary — only inject for non-English sessions, compact format
    if language and language != "en":
        glossary = load_glossary()
        terms = glossary.get("terms", [])
        if terms:
            lines = [f"## Terminology Reference ({language.upper()})", "",
                     "Use these exact translations. Do not paraphrase or use alternatives.", ""]
            for t in terms:
                translation = t.get("translations", {}).get(language, "")
                if translation:
                    lines.append(f"- {t['term']} → {translation}")
            if len(lines) > 4:  # only inject if we have at least one translation
                parts.append("\n".join(lines))

    # Organizations directory
    orgs = load_organizations()
    org_list = orgs.get("organizations", [])
    if org_list:
        lines = ["## Organizations Reference",  "",
                 "When naming an organization, use the exact name from this list. "
                 "Do not invent or approximate organization names. "
                 "The correct escalation path is always: worker → national union → UNI Global Union.", ""]

        for org in org_list:
            name = org.get("name", "")
            org_type = org.get("type", "")
            country = org.get("country", "")
            desc = org.get("description", "")

            line = f"- **{name}** [{org_type}, {country}]"
            if desc:
                line += f" — {desc}"
            lines.append(line)

        parts.append("\n".join(lines))

    if not parts:
        return ""
    return "\n\n".join(parts)


def assemble_system_prompt(survey: dict[str, Any] | None, language: str = "en", frontend_id: str | None = None) -> str:
    """Build the full system prompt from case-specific prompt files.

    Structure: core + guardrails + case prompt (profile+case) + context(survey) + knowledge base
    Sprint 8h: frontend_id used to resolve per-frontend prompts when mode is 'per_frontend'.
    Sprint 10: guardrails.md always injected between core and case prompt.
    """
    parts: list[str] = []

    # 1. Core system prompt (universal instructions)
    core = _load("core.md", frontend_id)
    if core:
        parts.append(core)

    # 2. Guardrails (always injected — safety net independent of other prompts)
    guardrails = _load("guardrails.md", frontend_id)
    if guardrails:
        parts.append(guardrails)

    if survey:
        # 3. Case-specific prompt (monolithic per profile+case)
        role = survey.get("role", "worker")
        mode = survey.get("type", "documentation")
        case_file = _resolve_case_prompt(role, mode)
        case_prompt = _load(case_file, frontend_id)
        logger.info(f"Case prompt: {case_file} for {role}/{mode} (frontend={frontend_id})")
        if case_prompt:
            parts.append(case_prompt)
        else:
            logger.warning(f"No case prompt found for {role}/{mode} ({case_file})")

        # 4. Context from survey data
        context = _render_context(survey, language, frontend_id)
        if context:
            parts.append(context)

    # 5. Knowledge base (glossary + organizations) — injected directly, not via RAG
    kb = _build_knowledge_section(survey, language)
    if kb:
        parts.append(kb)

    return "\n\n---\n\n".join(parts)
