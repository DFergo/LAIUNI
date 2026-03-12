"""Assembles the system prompt from case-specific prompt files + survey context + knowledge base.

Sprint 7c: Monolithic case prompts replace modular core+role+mode concatenation.
Sprint 8h: Per-frontend prompt sets (exclusive model — toggle Global / Per Frontend).
Structure: core.md + case prompt (per profile+case) + context_template + knowledge base.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.core.config import config

logger = logging.getLogger("backend.prompts")

# Default prompts shipped with the app — copied to data dir on first run
_DEFAULTS_DIR = Path(__file__).parent.parent / "prompts"

# Prompt mode config file
_PROMPT_MODE_PATH = Path("/app/data/prompt_mode.json")


def _prompts_dir(frontend_id: str | None = None) -> Path:
    """Resolve prompts directory based on prompt mode and frontend_id."""
    mode = get_prompt_mode()
    if mode == "per_frontend" and frontend_id:
        campaign_dir = Path(f"/app/data/campaigns/{frontend_id}/prompts")
        if campaign_dir.exists() and any(campaign_dir.glob("*.md")):
            return campaign_dir
        # Fallback to global if frontend has no custom prompts yet
        logger.debug(f"No custom prompts for frontend {frontend_id}, using global")
    return Path(config.prompts_path)


def _global_prompts_dir() -> Path:
    """Always return the global prompts directory (for admin, defaults, etc.)."""
    return Path(config.prompts_path)


def get_prompt_mode() -> str:
    """Get current prompt mode: 'global' or 'per_frontend'."""
    if _PROMPT_MODE_PATH.exists():
        try:
            data = json.loads(_PROMPT_MODE_PATH.read_text())
            return data.get("mode", "global")
        except Exception:
            pass
    return "global"


def set_prompt_mode(mode: str) -> str:
    """Set prompt mode. Returns the new mode."""
    if mode not in ("global", "per_frontend"):
        raise ValueError(f"Invalid prompt mode: {mode}")
    _PROMPT_MODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROMPT_MODE_PATH.write_text(json.dumps({"mode": mode}))
    logger.info(f"Prompt mode set to: {mode}")
    return mode


def copy_global_to_frontend(frontend_id: str) -> int:
    """Copy all global prompts to a frontend's campaign directory. Returns count."""
    global_dir = _global_prompts_dir()
    campaign_dir = Path(f"/app/data/campaigns/{frontend_id}/prompts")
    campaign_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src_file in global_dir.glob("*.md"):
        dst_file = campaign_dir / src_file.name
        if not dst_file.exists():
            dst_file.write_text(src_file.read_text())
            count += 1
    logger.info(f"Copied {count} global prompts to frontend {frontend_id}")
    return count


def delete_frontend_prompts(frontend_id: str) -> int:
    """Delete all custom prompts for a frontend. Returns count deleted."""
    campaign_dir = Path(f"/app/data/campaigns/{frontend_id}/prompts")
    if not campaign_dir.exists():
        return 0
    count = 0
    for f in campaign_dir.glob("*.md"):
        f.unlink()
        count += 1
    logger.info(f"Deleted {count} custom prompts for frontend {frontend_id}")
    return count


def frontend_has_custom_prompts(frontend_id: str) -> bool:
    """Check if a frontend has any custom prompt files."""
    campaign_dir = Path(f"/app/data/campaigns/{frontend_id}/prompts")
    return campaign_dir.exists() and any(campaign_dir.glob("*.md"))


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
    """Load a prompt file by name. Returns empty string if not found."""
    path = _prompts_dir(frontend_id) / name
    if path.exists():
        return path.read_text().strip()
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

    Structure: core + case prompt (profile+case) + context(survey) + knowledge base
    Sprint 8h: frontend_id used to resolve per-frontend prompts when mode is 'per_frontend'.
    """
    parts: list[str] = []

    # 1. Core system prompt (universal instructions)
    core = _load("core.md", frontend_id)
    if core:
        parts.append(core)

    if survey:
        # 2. Case-specific prompt (monolithic per profile+case)
        role = survey.get("role", "worker")
        mode = survey.get("type", "documentation")
        case_file = _resolve_case_prompt(role, mode)
        case_prompt = _load(case_file, frontend_id)
        logger.info(f"Case prompt: {case_file} for {role}/{mode} (frontend={frontend_id})")
        if case_prompt:
            parts.append(case_prompt)
        else:
            logger.warning(f"No case prompt found for {role}/{mode} ({case_file})")

        # 3. Context from survey data
        context = _render_context(survey, language, frontend_id)
        if context:
            parts.append(context)

    # 4. Knowledge base (glossary + organizations) — injected directly, not via RAG
    kb = _build_knowledge_section(survey, language)
    if kb:
        parts.append(kb)

    return "\n\n---\n\n".join(parts)
