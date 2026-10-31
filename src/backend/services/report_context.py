"""Case material for the internal documents (UNI summary, internal case file).

The chat uses the knowledge base to steer the conversation. The case file uses
it for something else: to classify the facts the user reported against the
global standards and codes of conduct (which instrument, which article). So the
case file gets its own retrieval, driven by the facts:

  1. extract the factual allegations from the conversation, survey and evidence
     (prompt ``report_facts.md``, reporter slot);
  2. retrieve candidate provisions for each fact from the global and campaign
     knowledge base (with the source document), plus supporting passages from
     the documents the user uploaded;
  3. hand the document generator a "case data" block (survey + evidence) and an
     "applicable standards" block (facts → provision IDs, then the provisions).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("backend.report_context")

_PROVISIONS_PER_FACT = 4
_EVIDENCE_PER_FACT = 2
_MAX_FACTS = 10
_MAX_PROVISION_CHARS = 3000
_MAX_STANDARDS_CHARS = 80000

_SURVEY_FIELDS = (
    ("role", "Role"), ("type", "Consultation mode"), ("name", "Name"), ("position", "Position"),
    ("union", "Union / organisation"), ("company", "Company (subject of the case)"),
    ("countryRegion", "Country / region"), ("description", "Situation description"),
)


def case_data_block(session: dict[str, Any] | None, evidence: list[dict[str, Any]]) -> str:
    """Survey answers + summaries of the user's uploaded documents/images."""
    parts = ["# Case data"]
    survey = (session or {}).get("survey") or {}
    lines = [f"- **{label}:** {survey[key]}" for key, label in _SURVEY_FIELDS if str(survey.get(key) or "").strip()]
    parts.append("## Intake survey\n" + ("\n".join(lines) if lines else "No survey data."))
    docs = [e for e in evidence if e.get("summary")]
    if docs:
        ev = ["## Evidence uploaded by the user"]
        for e in docs:
            kind = "image (described by a vision model)" if e.get("type") == "image" else "document"
            ev.append(f"### {e.get('filename', 'file')} — {kind}\n{e['summary']}")
        parts.append("\n\n".join(ev))
    unanalysed = [e.get("filename", "file") for e in evidence if not e.get("summary")]
    if unanalysed:
        parts.append("Files uploaded but not analysed: " + ", ".join(unanalysed))
    return "\n\n".join(parts)


def _parse_facts(text: str) -> tuple[str, list[str]]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return "", []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return "", []
    facts = [str(f).strip() for f in data.get("facts") or [] if str(f).strip()]
    return str(data.get("context") or "").strip(), facts[:_MAX_FACTS]


async def extract_facts(session_token: str, frontend_id: str, case_data: str, settings: dict[str, Any]) -> tuple[str, list[str]]:
    """(search context, facts). Falls back to the user's own messages if extraction fails."""
    from src.services.llm_provider import llm, build_fallback_chain
    from src.services.prompt_assembler import load_prompt
    from src.services.session_store import store as history

    conversation = [m for m in history.get_llm_messages(session_token) if m["role"] != "system"]
    transcript = "\n\n".join(f"[{m['role'].upper()}]: {m['content']}" for m in conversation
                             if isinstance(m.get("content"), str))
    instruction = load_prompt("report_facts.md", frontend_id)
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": f"{case_data}\n\n# Conversation\n\n{transcript}"},
    ]
    try:
        raw = await llm.chat_with_fallback(messages, build_fallback_chain(settings, "reporter"), session=session_token)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        context, facts = _parse_facts(raw)
        if facts:
            return context, facts
        logger.warning(f"[{session_token}] Fact extraction returned no facts; using the user's messages")
    except Exception as e:
        logger.warning(f"[{session_token}] Fact extraction failed ({e}); using the user's messages")
    users = sorted((m["content"] for m in conversation if m["role"] == "user" and isinstance(m.get("content"), str)),
                   key=len, reverse=True)
    return "", [u[:500] for u in users[:_MAX_FACTS]]


def standards_block(session_token: str, frontend_id: str, context: str, facts: list[str]) -> str:
    """Facts → candidate provisions (deduplicated, with source), plus supporting
    passages from the user's own documents."""
    from src.services.rag_service import get_relevant_sources
    from src.services.evidence_processor import get_session_rag_chunks

    provisions: list[dict[str, str]] = []
    index: dict[str, int] = {}
    fact_lines: list[str] = []
    evidence_lines: list[str] = []
    for i, fact in enumerate(facts, 1):
        query = f"{fact}\n{context}".strip()
        ids = []
        for src in get_relevant_sources(query, top_k=_PROVISIONS_PER_FACT, frontend_id=frontend_id or None):
            key = src["text"].strip()
            if key not in index:
                provisions.append(src)
                index[key] = len(provisions)
            ids.append(f"P{index[key]}")
        fact_lines.append(f"- **F{i}.** {fact}\n  Candidate provisions: {', '.join(dict.fromkeys(ids)) or 'none found'}")
        for passage in get_session_rag_chunks(session_token, fact, top_k=_EVIDENCE_PER_FACT):
            evidence_lines.append(f"- (F{i}) {passage.strip()[:_MAX_PROVISION_CHARS]}")

    out = ["# Applicable standards (retrieved from the knowledge base for each fact)",
           "## Facts reported", "\n".join(fact_lines) or "No facts identified."]
    if evidence_lines:
        out += ["## Passages from the user's documents relevant to each fact", "\n".join(evidence_lines)]
    out.append("## Provisions")
    used = sum(len(x) for x in out)
    for n, p in enumerate(provisions, 1):
        source = p["source"] or ("campaign document" if p["scope"] == "campaign" else "knowledge base")
        entry = f"[P{n}] (source: {source})\n{p['text'].strip()[:_MAX_PROVISION_CHARS]}"
        if used + len(entry) > _MAX_STANDARDS_CHARS:
            out.append(f"(… {len(provisions) - n + 1} further provisions omitted for length)")
            break
        out.append(entry)
        used += len(entry)
    return "\n\n".join(out)


CASE_FILE_INSTRUCTION = (
    "Use the case data and the evidence above together with the conversation. When you classify the facts "
    "against international standards or codes of conduct, use the provisions under 'Applicable standards': "
    "name the instrument and the article as they appear there and cite the provision ID (e.g. [P3]). If you "
    "rely on a standard that is not among those provisions, mark it '(not in the knowledge base)'. If no "
    "provision supports a fact, say so."
)


async def build(session_token: str, frontend_id: str, settings: dict[str, Any], with_standards: bool) -> tuple[str, str]:
    """(case data block, standards block or ""). Never raises: a failure only
    drops the extra material, the document is still generated."""
    from src.services.session_store import store as history
    from src.services.evidence_processor import load_evidence_context

    case_data = ""
    try:
        case_data = case_data_block(history.get_session(session_token), load_evidence_context(session_token))
    except Exception as e:
        logger.error(f"[{session_token}] Case data block failed: {e}")
    if not with_standards:
        return case_data, ""
    try:
        context, facts = await extract_facts(session_token, frontend_id, case_data, settings)
        standards = standards_block(session_token, frontend_id, context, facts)
        logger.info(f"[{session_token}] Case file standards: {len(facts)} facts, block {len(standards)} chars")
        return case_data, standards
    except Exception as e:
        logger.error(f"[{session_token}] Standards retrieval failed: {e}")
        return case_data, ""
