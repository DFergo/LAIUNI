"""Multi-step preparation of the internal case file (Sprint 39).

A single generation pass over a 15–20 turn conversation cannot both organise the
case and classify every fact against the standards. So before the case file is
written (with the unchanged template ``internal_case_file.md``):

  1. Analysis — one call over the conversation, survey and evidence
     (``report_analysis.md``): context, parties, chronology, facts, gaps.
  2. Research — per fact, in parallel: retrieve candidate provisions from the
     knowledge base (global + campaign, with source) and the user's documents;
     the model classifies the fact (``report_research.md``) or asks for more
     searches (bounded rounds).
  3. Review — deterministic: every cited provision ID must exist and the quote
     the model gives must appear in that provision's text; otherwise the link is
     downgraded to "possible" and flagged.
  4. Writing — the case file template receives the analysis, the reviewed
     classifications and only the provisions cited (see ``writer_material``).

The code fixes the structure; the model reasons inside each step. Searches are
requested as plain JSON, so it works on every provider (no native tool calling).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("backend.case_file_pipeline")

MAX_FACTS = 12
MAX_SEARCH_ROUNDS = 2          # extra rounds the model may request per fact
MAX_QUERIES_PER_ROUND = 3
PROVISIONS_PER_SEARCH = 4
EVIDENCE_PER_FACT = 2
FACT_CONCURRENCY = 3
MAX_PROVISION_CHARS = 3000
STRENGTHS = ("clear", "probable", "possible")

WRITER_INSTRUCTION = (
    "Write the case file using exactly the sections and headings of the template, in the same order — do not add, "
    "rename or merge sections. Use the case analysis above to fill them: the primary violation type and dates in "
    "section 3; the classifications in section 4 under the heading of the matching instrument (ILO, OECD, any module "
    "section, CSDDD, UNGP), citing the provision ID (e.g. [P3]) and the article; codes of conduct and other instruments "
    "where they fit best; standards marked as not in the knowledge base keep that mark; the chronology in section 5; "
    "the information gaps in section 11 (critical evidence gaps) and section 13 (discrepancy notes); the strength of "
    "each classification informs the case strength in section 13. Links flagged as unverified must not be presented "
    "as established."
)


# --------------------------------------------------------------------------- helpers

def _json_from(text: str) -> dict[str, Any] | None:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip(" .\"'“”")


async def _ask(messages: list[dict[str, Any]], settings: dict[str, Any], session: str) -> str:
    from src.services.llm_provider import llm, build_fallback_chain
    return await llm.chat_with_fallback(messages, build_fallback_chain(settings, "reporter"), session=session)


class Catalog:
    """Provisions retrieved during research, shared across facts: one ID each."""

    def __init__(self):
        self.items: list[dict[str, str]] = []
        self._index: dict[str, str] = {}

    def add(self, src: dict[str, str]) -> str:
        key = src["text"].strip()
        if key not in self._index:
            self.items.append(src)
            self._index[key] = f"P{len(self.items)}"
        return self._index[key]

    def get(self, pid: str) -> dict[str, str] | None:
        m = re.fullmatch(r"\[?P(\d+)\]?", (pid or "").strip())
        if not m or not 1 <= int(m.group(1)) <= len(self.items):
            return None
        return self.items[int(m.group(1)) - 1]

    def render(self, pid: str) -> str:
        p = self.get(pid)
        source = p["source"] or ("campaign document" if p["scope"] == "campaign" else "knowledge base")
        return f"[{pid}] (source: {source})\n{p['text'].strip()[:MAX_PROVISION_CHARS]}"


# --------------------------------------------------------------------------- 1. analysis

async def analyse(session_token: str, frontend_id: str, case_data: str, transcript: str,
                  settings: dict[str, Any]) -> dict[str, Any] | None:
    from src.services.prompt_assembler import load_prompt
    messages = [
        {"role": "system", "content": load_prompt("report_analysis.md", frontend_id or None)},
        {"role": "user", "content": f"{case_data}\n\n# Conversation\n\n{transcript}"},
    ]
    data = _json_from(await _ask(messages, settings, session_token))
    if not data or not data.get("facts"):
        return None
    facts = []
    for i, f in enumerate(data["facts"][:MAX_FACTS], 1):
        stmt = (f.get("statement") if isinstance(f, dict) else str(f)) or ""
        if stmt.strip():
            facts.append({"id": f"F{i}", "statement": stmt.strip(),
                          "evidence": [str(e) for e in (f.get("evidence") or [])] if isinstance(f, dict) else []})
    data["facts"] = facts
    return data if facts else None


# --------------------------------------------------------------------------- 2. research

async def _search(query: str, frontend_id: str, catalog: Catalog) -> list[str]:
    """Retrieval embeds the query (possibly over the network): run it in a thread
    so the event loop — chat streaming, polling — is never blocked."""
    from src.services.rag_service import get_relevant_sources
    found = await asyncio.to_thread(get_relevant_sources, query, PROVISIONS_PER_SEARCH, frontend_id or None)
    return [catalog.add(src) for src in found]


async def research_fact(fact: dict[str, Any], context: str, session_token: str, frontend_id: str,
                        settings: dict[str, Any], catalog: Catalog) -> dict[str, Any]:
    from src.services.prompt_assembler import load_prompt
    from src.services.evidence_processor import get_session_rag_chunks

    shown: list[str] = list(dict.fromkeys(await _search(f"{fact['statement']}\n{context}", frontend_id, catalog)))
    passages = await asyncio.to_thread(get_session_rag_chunks, session_token, fact["statement"], EVIDENCE_PER_FACT)
    instruction = load_prompt("report_research.md", frontend_id or None)
    searches: list[str] = []
    result: dict[str, Any] | None = None
    note = ""

    for round_no in range(MAX_SEARCH_ROUNDS + 1):
        last = round_no == MAX_SEARCH_ROUNDS
        body = [f"# Fact {fact['id']}\n{fact['statement']}", f"# Context\n{context or 'not stated'}"]
        if fact.get("evidence"):
            body.append("# Supporting material from the conversation\n" + "\n".join(f"- {e}" for e in fact["evidence"]))
        if passages:
            body.append("# Passages from the user's documents\n" + "\n".join(f"- {p.strip()[:1500]}" for p in passages))
        body.append("# Provisions retrieved\n\n" + ("\n\n".join(catalog.render(pid) for pid in shown) or "None found."))
        if note:
            body.append(note)
        if last:
            body.append("This is the final round: classify with the provisions above; do not ask for more searches.")
        data = _json_from(await _ask([{"role": "system", "content": instruction},
                                      {"role": "user", "content": "\n\n".join(body)}], settings, session_token))
        if data is None:
            break
        queries = [str(q).strip() for q in (data.get("more_searches") or []) if str(q).strip()]
        if queries and not last and "classifications" not in data:
            await _run_searches(queries, context, frontend_id, catalog, shown, searches)
            continue
        # Before accepting "not in the knowledge base", look those standards up
        # once by name: if that finds provisions not yet shown, re-ask.
        missing = [n for n in data.get("not_in_knowledge_base") or [] if isinstance(n, dict)]
        if missing and not searches and not last:
            queries = [f"{n.get('instrument', '')} {n.get('article', '')}".strip() for n in missing]
            if await _run_searches([q for q in queries if q], context, frontend_id, catalog, shown, searches):
                note = ("The standards you listed as not in the knowledge base were searched for by name; any "
                        "provisions found have been added above. Classify again with them.")
                continue
        result = data
        break

    return review(fact, result or {}, shown, catalog, searches)


async def _run_searches(queries: list[str], context: str, frontend_id: str, catalog: Catalog,
                        shown: list[str], searches: list[str]) -> bool:
    """Run up to MAX_QUERIES_PER_ROUND searches; True if new provisions were found."""
    found = False
    for q in queries[:MAX_QUERIES_PER_ROUND]:
        searches.append(q)
        for pid in await _search(f"{q}\n{context}", frontend_id, catalog):
            if pid not in shown:
                shown.append(pid)
                found = True
    return found


# --------------------------------------------------------------------------- 3. review

def review(fact: dict[str, Any], data: dict[str, Any], shown: list[str], catalog: Catalog,
           searches: list[str]) -> dict[str, Any]:
    """Keep only links to provisions that were shown; verify each quote against the text."""
    links, not_in_kb = [], list(data.get("not_in_knowledge_base") or [])
    for c in data.get("classifications") or []:
        if not isinstance(c, dict):
            continue
        pid = re.sub(r"[\[\]\s]", "", str(c.get("provision", "")))
        prov = catalog.get(pid)
        if prov is None or pid not in shown:
            not_in_kb.append({"instrument": c.get("instrument", ""), "article": c.get("article", ""),
                              "reasoning": f"{c.get('reasoning', '')} (cited an unknown provision ID {c.get('provision')})"})
            continue
        strength = str(c.get("strength", "possible")).lower()
        strength = strength if strength in STRENGTHS else "possible"
        quote = str(c.get("quote", ""))
        verified = bool(_norm(quote)) and _norm(quote) in _norm(prov["text"])
        if not verified:
            strength = "possible"
        links.append({**{k: c.get(k, "") for k in ("instrument", "article", "violation_type", "reasoning")},
                      "provision": pid, "strength": strength, "quote": quote, "verified": verified})
    return {"fact": fact, "links": links, "not_in_knowledge_base": not_in_kb,
            "missing_information": [str(m) for m in data.get("missing_information") or []],
            "searches": searches, "provisions_shown": shown, "answered": bool(data)}


# --------------------------------------------------------------------------- 4. material for the writer

def writer_material(analysis: dict[str, Any], research: list[dict[str, Any]], catalog: Catalog) -> str:
    ctx = analysis.get("context") or {}
    out = ["# Case analysis (prepared in steps from the conversation, survey and evidence)"]
    if isinstance(ctx, dict) and any(ctx.values()):
        out.append("## Context\n" + "\n".join(f"- {k}: {v}" for k, v in ctx.items() if v))
    parties = [p for p in analysis.get("parties") or [] if isinstance(p, dict)]
    if parties:
        out.append("## Parties\n" + "\n".join(f"- {p.get('name', '')}: {p.get('role', '')}" for p in parties))
    timeline = [t for t in analysis.get("timeline") or [] if isinstance(t, dict)]
    if timeline:
        out.append("## Chronology\n" + "\n".join(
            f"- {t.get('when') or 'date unknown'} — {t.get('event', '')} ({t.get('source', 'user')})" for t in timeline))
    cited: list[str] = []
    fact_blocks = []
    for r in research:
        f = r["fact"]
        lines = [f"### {f['id']}. {f['statement']}"]
        if f.get("evidence"):
            lines.append("Supported by: " + "; ".join(f["evidence"]))
        for link in r["links"]:
            cited.append(link["provision"])
            flag = "" if link["verified"] else " — UNVERIFIED (quote not found in the provision)"
            lines.append(f"- [{link['provision']}] {link['instrument']} {link['article']} — {link['violation_type']} — "
                         f"strength: {link['strength']}{flag}. {link['reasoning']}")
        for n in r["not_in_knowledge_base"]:
            if isinstance(n, dict):
                lines.append(f"- (not in the knowledge base) {n.get('instrument', '')} {n.get('article', '')}. {n.get('reasoning', '')}")
        if not r["links"] and not r["not_in_knowledge_base"]:
            lines.append("- No supporting provision found in the knowledge base.")
        if r["missing_information"]:
            lines.append("Missing to establish it more firmly: " + "; ".join(r["missing_information"]))
        fact_blocks.append("\n".join(lines))
    out.append("## Facts and classification\n\n" + "\n\n".join(fact_blocks))
    gaps = [str(g) for g in analysis.get("gaps") or [] if str(g).strip()]
    if gaps:
        out.append("## Information gaps\n" + "\n".join(f"- {g}" for g in gaps))
    if cited:
        out.append("## Provisions cited\n\n" + "\n\n".join(catalog.render(pid) for pid in dict.fromkeys(cited)))
    return "\n\n".join(out)


# --------------------------------------------------------------------------- orchestration

async def prepare(session_token: str, frontend_id: str, case_data: str, settings: dict[str, Any]) -> str | None:
    """Run steps 1–3 and return the writer material, or None if the analysis
    failed (the caller then falls back to the single-pass retrieval)."""
    from src.services.session_store import store as history

    t0 = time.time()
    conversation = [m for m in history.get_llm_messages(session_token) if m["role"] != "system"]
    transcript = "\n\n".join(f"[{m['role'].upper()}]: {m['content']}" for m in conversation
                             if isinstance(m.get("content"), str))
    analysis = await analyse(session_token, frontend_id, case_data, transcript, settings)
    if analysis is None:
        logger.warning(f"[{session_token}] Case analysis failed; falling back to single-pass retrieval")
        return None
    ctx = analysis.get("context") or {}
    context = ", ".join(str(v) for v in ctx.values() if v) if isinstance(ctx, dict) else str(ctx)

    catalog = Catalog()
    sem = asyncio.Semaphore(FACT_CONCURRENCY)

    async def one(fact):
        async with sem:
            try:
                return await research_fact(fact, context, session_token, frontend_id, settings, catalog)
            except Exception as e:
                logger.warning(f"[{session_token}] Research failed for {fact['id']}: {e}")
                return review(fact, {}, [], catalog, [])

    research = await asyncio.gather(*(one(f) for f in analysis["facts"]))
    material = writer_material(analysis, research, catalog)

    links = [link for r in research for link in r["links"]]
    stats = {"facts": len(research), "links": len(links), "verified": sum(link["verified"] for link in links),
             "provisions_retrieved": len(catalog.items), "extra_searches": sum(len(r["searches"]) for r in research),
             "seconds": round(time.time() - t0, 1)}
    _save(session_token, {"analysis": analysis, "research": research, "stats": stats})
    logger.info(f"[{session_token}] Case file prepared: {stats}")
    return material


def _save(session_token: str, data: dict[str, Any]):
    try:
        from src.core.paths import SESSIONS_DIR
        d = SESSIONS_DIR / session_token
        if d.exists():
            tmp = d / "case_analysis.json.tmp"
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            tmp.rename(d / "case_analysis.json")
    except Exception as e:
        logger.warning(f"[{session_token}] Could not save case analysis: {e}")
