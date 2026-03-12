"""Branding translator — uses LLM to translate custom branding text to all supported languages.

Sprint 11: Background translation of disclaimer and instructions text for per-frontend branding.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.services.llm_provider import llm

logger = logging.getLogger("backend.branding_translator")

_CAMPAIGNS_DIR = Path("/app/data/campaigns")

# All supported languages (must match frontend i18n.ts)
LANGUAGES = [
    ("en", "English"), ("zh", "Chinese (Simplified)"), ("hi", "Hindi"),
    ("es", "Spanish"), ("ar", "Arabic"), ("fr", "French"),
    ("bn", "Bengali"), ("pt", "Portuguese"), ("ru", "Russian"),
    ("id", "Indonesian"), ("de", "German"), ("mr", "Marathi"),
    ("ja", "Japanese"), ("te", "Telugu"), ("tr", "Turkish"),
    ("ta", "Tamil"), ("vi", "Vietnamese"), ("ko", "Korean"),
    ("ur", "Urdu"), ("th", "Thai"), ("it", "Italian"),
    ("pl", "Polish"), ("nl", "Dutch"), ("el", "Greek"),
    ("uk", "Ukrainian"), ("ro", "Romanian"), ("hr", "Croatian"),
    ("xh", "Xhosa"), ("sw", "Swahili"), ("hu", "Hungarian"),
    ("sv", "Swedish"),
]

# In-memory translation status per frontend
_translation_status: dict[str, dict[str, Any]] = {}


def get_translation_status(frontend_id: str) -> dict[str, Any]:
    return _translation_status.get(frontend_id, {"status": "idle", "progress": 0, "total": 0})


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def _translate_text(text: str, target_lang: str, target_name: str) -> str:
    """Translate a single text to target language using LLM."""
    messages = [
        {
            "role": "system",
            "content": "You are a professional translator. Translate the given text accurately. "
                       "Preserve all formatting, line breaks, and meaning. "
                       "Return ONLY the translation, no commentary or explanations.",
        },
        {
            "role": "user",
            "content": f"Translate the following text to {target_name} ({target_lang}):\n\n{text}",
        },
    ]
    try:
        result = await llm.chat(messages, temperature=0.3, max_tokens=2048)
        return _strip_think_blocks(result)
    except Exception as e:
        logger.warning(f"Translation to {target_name} failed: {e}")
        return ""


async def translate_branding(frontend_id: str, branding: dict[str, str]):
    """Translate branding texts to all supported languages. Saves to disk.

    Args:
        frontend_id: The frontend to translate for
        branding: Dict with disclaimer_text and instructions_text (source language)
    """
    disclaimer = branding.get("disclaimer_text", "")
    instructions = branding.get("instructions_text", "")

    if not disclaimer and not instructions:
        return

    total = len(LANGUAGES)
    _translation_status[frontend_id] = {"status": "translating", "progress": 0, "total": total}

    translations: dict[str, dict[str, str]] = {}

    for i, (code, name) in enumerate(LANGUAGES):
        entry: dict[str, str] = {}

        if disclaimer:
            # Detect source language: if the source text matches this language, skip translation
            if code == "en":
                # Assume source is likely English; save as-is
                entry["disclaimer_text"] = disclaimer
            else:
                entry["disclaimer_text"] = await _translate_text(disclaimer, code, name)

        if instructions:
            if code == "en":
                entry["instructions_text"] = instructions
            else:
                entry["instructions_text"] = await _translate_text(instructions, code, name)

        translations[code] = entry
        _translation_status[frontend_id] = {"status": "translating", "progress": i + 1, "total": total}
        logger.info(f"Translated branding for {frontend_id}: {name} ({i + 1}/{total})")

    # Save to disk (atomic)
    path = _CAMPAIGNS_DIR / frontend_id / "branding_translations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(translations, ensure_ascii=False, indent=2))
    tmp.rename(path)

    _translation_status[frontend_id] = {"status": "done", "progress": total, "total": total}
    logger.info(f"Branding translations complete for {frontend_id}: {total} languages")


def load_translations(frontend_id: str) -> dict[str, dict[str, str]] | None:
    """Load saved translations from disk. Returns None if no translations exist."""
    path = _CAMPAIGNS_DIR / frontend_id / "branding_translations.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def delete_translations(frontend_id: str):
    """Delete translation files for a frontend (reset to default)."""
    path = _CAMPAIGNS_DIR / frontend_id / "branding_translations.json"
    if path.exists():
        path.unlink()
        logger.info(f"Branding translations deleted for {frontend_id}")
