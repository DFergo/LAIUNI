"""Assembles the system prompt from modular prompt files + survey context + knowledge base."""

import json
import logging
from pathlib import Path
from typing import Any

from src.core.config import config

logger = logging.getLogger("backend.prompts")

# Default prompts shipped with the app — copied to data dir on first run
_DEFAULTS_DIR = Path(__file__).parent.parent / "prompts"


def _prompts_dir() -> Path:
    return Path(config.prompts_path)


def ensure_defaults():
    """Copy default prompt files to data dir if they don't exist yet."""
    dest = _prompts_dir()
    dest.mkdir(parents=True, exist_ok=True)
    for src_file in _DEFAULTS_DIR.glob("*.md"):
        dst_file = dest / src_file.name
        if not dst_file.exists():
            dst_file.write_text(src_file.read_text())
            logger.info(f"Installed default prompt: {src_file.name}")


def _load(name: str) -> str:
    """Load a prompt file by name. Returns empty string if not found."""
    path = _prompts_dir() / name
    if path.exists():
        return path.read_text().strip()
    logger.warning(f"Prompt file not found: {name}")
    return ""


def _render_context(survey: dict[str, Any] | None, language: str) -> str:
    """Render context_template.md with survey data."""
    template = _load("context_template.md")
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


def assemble_system_prompt(survey: dict[str, Any] | None, language: str = "en") -> str:
    """Build the full system prompt from modular files.

    Order: core + role + mode + context(survey)
    """
    parts: list[str] = []

    # 1. Core system prompt
    core = _load("core.md")
    if core:
        parts.append(core)

    if survey:
        # 2. Role-specific prompt
        role = survey.get("role", "worker")
        role_file = f"{role}.md"
        # Map 'representative' role to 'worker_representative.md'
        if role == "representative":
            role_file = "worker_representative.md"
        role_prompt = _load(role_file)
        if role_prompt:
            parts.append(role_prompt)

        # 3. Mode-specific prompt
        mode = survey.get("type", "documentation")
        mode_prompt = _load(f"{mode}.md")
        if mode_prompt:
            parts.append(mode_prompt)

        # 4. Context from survey data
        context = _render_context(survey, language)
        if context:
            parts.append(context)

    # 5. Knowledge base (glossary + organizations) — injected directly, not via RAG
    kb = _build_knowledge_section(survey, language)
    if kb:
        parts.append(kb)

    return "\n\n---\n\n".join(parts)
