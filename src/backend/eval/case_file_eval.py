"""Compare internal case files across preparation methods on the test cases.

Variants (all through the real document path, same template and model):
  A  conversation only (how case files were made before Sprint 38)
  B  single pass: facts → one retrieval per fact (Sprint 38)
  C  multi-step: analysis → research per fact → review (Sprint 39)

Writes every case file to <out>/<case>/<variant>.md (plus C's analysis JSON) and
<out>/summary.md with metrics: template compliance, citations (valid / total),
standards marked as outside the knowledge base, LLM calls, tokens and time.
Quality is for a human reviewer: the summary only measures what can be counted.

Run in the backend image, with the reporter model given by environment:
    docker run --rm -e EVAL_BASE_URL=https://api.mistral.ai/v1 -e EVAL_API_KEY=... \
        -e EVAL_MODEL=mistral-large-4 -e PYTHONPATH=/app \
        -v "$PWD/src/backend:/app/src" -v "$OUT:/out" -w /app ghcr.io/dfergo/laiuni-backend:latest \
        python -m src.eval.case_file_eval /out [case-name-filter]
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HRDD_DATA_DIR", tempfile.mkdtemp(prefix="hrdd-eval-"))

from src.core.paths import PROMPTS_DIR, SESSIONS_DIR  # noqa: E402

CASES = Path(__file__).parent / "cases"
VARIANTS = {"A": "conversation only", "B": "single-pass retrieval", "C": "multi-step"}


def _setup():
    if not PROMPTS_DIR.exists():
        shutil.copytree(Path(__file__).parent.parent / "prompts", PROMPTS_DIR)
    from src.services.connection_registry import connections
    from src.api.v1.admin import llm as llm_admin
    if not connections.get("eval"):
        connections.add({"id": "eval", "type": "openai", "base_url": os.environ["EVAL_BASE_URL"],
                         "api_key": os.environ.get("EVAL_API_KEY", "")})
    s = llm_admin._load_settings()
    model = os.environ.get("EVAL_MODEL", "mistral-large-4")
    s.update({"inference_connection": "eval", "inference_model": model, "reporter_connection": "eval",
              "reporter_model": model, "inference_fallback_enabled": False, "summariser_enabled": False})
    llm_admin._save_settings(s)
    return s


def _headings(text: str) -> list[str]:
    return [_title(h) for h in re.findall(r"^#{2,3}\s+(.+?)\s*$", text, re.M)]


def _title(h: str) -> str:
    return re.sub(r"^[\d.\s]+", "", re.sub(r"[*_`]", "", h)).strip().lower()


def _metrics(report: str, expected: list[str], catalog_ids: set[str]) -> dict:
    got = _headings(report)
    cites = re.findall(r"\[P(\d+)\]", report)
    return {
        "chars": len(report),
        "missing_sections": [h for h in expected if h not in got],
        "extra_headings": sorted({h for h in got if h not in expected}),
        "citations": len(cites),
        "distinct_citations": len(set(cites)),
        "invalid_citations": sorted({f"P{c}" for c in cites if f"P{c}" not in catalog_ids}),
        "not_in_kb_marks": len(re.findall(r"not in (the )?knowledge base", report, re.I)),
    }


async def _run_variant(case_name: str, case: dict, variant: str, settings: dict, fid: str) -> dict:
    from src.services import polling, report_context, evidence_processor, llm_usage
    from src.services.prompt_assembler import load_prompt

    token = f"EVAL-{case_name[:2]}{variant}-{int(time.time()) % 100000:05d}"
    h = polling.history
    h.init_session(token, "x", case["survey"], "en", "eval", fid)
    for role, content in case["conversation"]:
        h.add_message(token, role, content)
    (SESSIONS_DIR / token).mkdir(parents=True, exist_ok=True)
    evidence_processor.load_evidence_context = lambda t, _e=case.get("evidence", []): _e

    t0 = time.time()
    material, instruction, case_data = "", "", ""
    if variant in ("B", "C"):
        case_data, material, instruction = await report_context.build(token, fid, settings, True, pipeline=(variant == "C"))
    report = await polling._generate_document(
        token, "internal_case_file.md", "en", settings, slot="reporter", frontend_id=fid,
        case_material="\n\n".join(x for x in (case_data, material) if x), extra_instruction=instruction,
    ) or ""
    seconds = round(time.time() - t0, 1)

    catalog_ids = set(re.findall(r"^\[(P\d+)\] \(source:", material, re.M))
    expected = [_title(h) for h in re.findall(r"^#{2,3}\s+(.+?)\s*$", load_prompt("internal_case_file.md", fid), re.M)]
    usage = llm_usage.session_summary(token).get("reporter", {})
    analysis = SESSIONS_DIR / token / "case_analysis.json"
    return {"report": report, "seconds": seconds, "calls": usage.get("calls", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0),
            "analysis": json.loads(analysis.read_text()) if analysis.exists() else None,
            "pipeline_used": variant == "C" and analysis.exists(),
            **_metrics(report, expected, catalog_ids)}


async def main(out: Path, name_filter: str = ""):
    settings = _setup()
    from src.services.frontend_registry import registry
    fid = registry.register("http://eval-frontend:8080", "eval")["id"]
    rows = []
    for path in sorted(CASES.glob("*.json")):
        if name_filter and name_filter not in path.stem:
            continue
        case = json.loads(path.read_text())
        (out / path.stem).mkdir(parents=True, exist_ok=True)
        for variant in VARIANTS:
            print(f"{path.stem} {variant} …", flush=True)
            try:
                r = await _run_variant(path.stem, case, variant, settings, fid)
            except Exception as e:
                print(f"  failed: {e}", flush=True)
                rows.append({"case": path.stem, "variant": variant, "error": str(e)})
                continue
            (out / path.stem / f"{variant}.md").write_text(r.pop("report"))
            analysis = r.pop("analysis")
            if analysis:
                (out / path.stem / "C_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=1))
            rows.append({"case": path.stem, "variant": variant, **r})
            print(f"  {r['seconds']} s, {r['calls']} calls, {r['citations']} citations, "
                  f"missing {len(r['missing_sections'])}, extra {len(r['extra_headings'])}", flush=True)
    (out / "metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    (out / "summary.md").write_text(_summary(rows))
    print(f"Done: {out / 'summary.md'}")


def _summary(rows: list[dict]) -> str:
    lines = ["# Case file comparison", "",
             f"Model: `{os.environ.get('EVAL_MODEL', 'mistral-large-4')}`. Variants: "
             + "; ".join(f"**{k}** = {v}" for k, v in VARIANTS.items()) + ".", "",
             "| Case | Var. | Time (s) | LLM calls | Prompt tok. | Completion tok. | Citations (distinct) | Invalid | Not-in-KB marks | Missing sections | Extra headings | Chars |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['case']} | {r['variant']} | error: {r['error'][:60]} |||||||||||")
            continue
        lines.append(f"| {r['case']} | {r['variant']} | {r['seconds']} | {r['calls']} | {r['prompt_tokens']:,} | "
                     f"{r['completion_tokens']:,} | {r['citations']} ({r['distinct_citations']}) | "
                     f"{len(r['invalid_citations'])} | {r['not_in_kb_marks']} | {len(r['missing_sections'])} | "
                     f"{len(r['extra_headings'])} | {r['chars']:,} |")
    lines += ["", "## Totals per variant", "", "| Var. | Time (s) | LLM calls | Prompt tok. | Citations | Invalid | Missing sections | Extra headings |",
              "|---|---|---|---|---|---|---|---|"]
    for v in VARIANTS:
        rs = [r for r in rows if r.get("variant") == v and "error" not in r]
        if rs:
            lines.append(f"| {v} | {sum(r['seconds'] for r in rs):.0f} | {sum(r['calls'] for r in rs)} | "
                         f"{sum(r['prompt_tokens'] for r in rs):,} | {sum(r['citations'] for r in rs)} | "
                         f"{sum(len(r['invalid_citations']) for r in rs)} | {sum(len(r['missing_sections']) for r in rs)} | "
                         f"{sum(len(r['extra_headings']) for r in rs)} |")
    lines += ["", "Extra headings are headings not in the template (module sections count as template). "
              "Read the reports in each case folder; C_analysis.json shows the chronology, facts, classifications "
              "(with quote verification) and gaps the multi-step method produced."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else ""))
