"""Step 2 — Triage: classify the document and identify which pages / table structures to hydrate.

One cheap LLM call over compact per-page digests (not the full text). Output drives sharding and
context construction in the extraction step. Falls back to keyword heuristics when the LLM is unavailable.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional

from app.clients.llm_client import LLMClient
from app.models.schemas import PageContent, PageTriage, TriageResult
from app.services.prompt_loader import render

logger = logging.getLogger(__name__)

HEAD_CHARS = 420
TABLE_HEADER_CHARS = 220
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")

KEYWORDS: Dict[str, List[str]] = {
    "BENEFIT_SCHEDULE": ["แผนที่", "แผน 0", "ผลประโยชน์", "ความคุ้มครอง", "ค่าห้อง", "ทุนประกัน", "plan", "benefit", "room"],
    "CLAIMS": ["เคลม", "สินไหม", "claim", "incurred", "paid", "icd", "loss ratio", "โรงพยาบาล", "diagnosis"],
    "CENSUS": ["employee", "รหัสพนักงาน", "date of birth", "วันเกิด", "sex", "เพศ", "salary", "เงินเดือน", "census", "อายุ"],
}


def _one_line(text: str, limit: int) -> str:
    text = re.sub(r"<!--.*?-->", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def build_digests(pages: List[PageContent]) -> str:
    blocks: List[str] = []
    for p in pages:
        numbers = len(NUM_RE.findall(p.markdown))
        lines = [f"### Page {p.page_no} (source: {p.source_file}) — {len(p.markdown)} chars · {len(p.tables)} tables · {numbers} numeric tokens",
                 f"Head: {_one_line(p.markdown, HEAD_CHARS)}"]
        for i, grid in enumerate(p.tables[:4], start=1):
            rows = len(grid)
            cols = len(grid[0]) if grid else 0
            header_rows = [" | ".join(c for c in r if c)[:TABLE_HEADER_CHARS] for r in grid[:2]]
            first_col = " / ".join(r[0] for r in grid[2:7] if r and r[0])[:TABLE_HEADER_CHARS]
            lines.append(f"Table {i} ({rows} rows x {cols} cols) top rows: {' // '.join(header_rows)}")
            if first_col:
                lines.append(f"  first-column labels: {first_col}")
        if not p.tables:
            pipe_rows = [ln for ln in p.markdown.splitlines() if ln.strip().startswith("|")][:2]
            if pipe_rows:
                lines.append("Markdown table top rows: " + " // ".join(_one_line(r, TABLE_HEADER_CHARS) for r in pipe_rows))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def heuristic_classify(pages: List[PageContent]) -> tuple[str, float]:
    text = "\n".join(p.markdown for p in pages).lower()
    scores = {dt: sum(text.count(k.lower()) for k in kws) for dt, kws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    return best, round(scores[best] / total, 2)


class TriageService:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or LLMClient()

    async def triage(self, pages: List[PageContent], hint: Optional[str] = None) -> TriageResult:
        start = time.perf_counter()
        digests = build_digests(pages)
        if not self.llm.enabled:
            result = self._fallback(pages, hint, reason="LLM not configured — heuristic triage")
        else:
            try:
                user = (f"Operator document-type hint: {hint or 'none'}\n\n"
                        f"Total pages: {len(pages)}\n\n# Page digests\n\n{digests}")
                result = await self.llm.structured(render("triage"), user, TriageResult, reasoning_effort="low", label="triage")
            except Exception as exc:
                logger.exception("Triage LLM call failed, using heuristic fallback: %s", exc)
                result = self._fallback(pages, hint, reason=f"triage LLM failed: {exc}")
        result = self._repair(result, pages, hint)
        logger.info("Triage: %s in %.0f ms — relevant pages: %s", result.document_type,
                    (time.perf_counter() - start) * 1000, [p.page for p in result.pages if p.is_relevant])
        return result

    def _fallback(self, pages: List[PageContent], hint: Optional[str], reason: str) -> TriageResult:
        doc_type, _ = heuristic_classify(pages)
        return TriageResult(
            document_type=hint or doc_type, reasoning=reason, source_hint=None,
            pages=[PageTriage(page=p.page_no, role="OTHER", is_relevant=True, summary="heuristic") for p in pages],
        )

    @staticmethod
    def _fix_plan_sequence(pages: List[PageTriage], result: TriageResult) -> None:
        """OCR digit confusion in headers (8→3, 7→1): a later section that repeats a plan number already used by an
        earlier section, while its neighbours run consecutively, gets the number implied by its position."""
        seen: set = set()
        fixes: List[str] = []
        fixed_headers: Dict[tuple, List[str]] = {}  # raw header tuple -> corrected labels (applied to every page printing it)
        for pt in pages:
            raw = tuple(pt.plan_columns)
            if raw in fixed_headers:
                pt.plan_columns = list(fixed_headers[raw])
                continue
            nums = [(i, int(m.group(0))) for i, c in enumerate(pt.plan_columns) for m in [re.search(r"\d+", c)] if m]
            if len(nums) != len(pt.plan_columns) or not nums:
                continue
            values = [n for _, n in nums]
            if seen and any(v in seen for v in values) and not all(v in seen for v in values):
                for idx, (i, v) in enumerate(nums):
                    if v in seen:
                        implied = (values[idx + 1] - 1) if idx + 1 < len(values) else (values[idx - 1] + 1)
                        if implied not in seen and implied not in values:
                            fixes.append(f"page {pt.page}: '{pt.plan_columns[i]}' → {implied}")
                            pt.plan_columns[i] = re.sub(r"\d+", str(implied), pt.plan_columns[i], count=1)
                            values[idx] = implied
            if list(raw) != pt.plan_columns:
                fixed_headers[raw] = list(pt.plan_columns)
            seen.update(values)
        if fixes:
            result.reasoning += " | Header digit fixes (OCR): " + "; ".join(fixes)

    @staticmethod
    def _prune_empty_plan_columns(pages_triage: List[PageTriage], pages_content: List[PageContent]) -> None:
        """Drop trailing unused plan columns that contain no real numeric values (only dashes or blanks)."""
        by_no = {p.page_no: p for p in pages_content}
        for pt in pages_triage:
            if not pt.plan_columns or pt.page not in by_no:
                continue
            p = by_no[pt.page]
            if not p.tables:
                continue
            tbl = p.tables[0]
            header_idx = None
            for r_idx, row in enumerate(tbl[:5]):
                if any(col in row for col in pt.plan_columns):
                    header_idx = r_idx
                    break
            if header_idx is None:
                continue
            while pt.plan_columns:
                last_col = pt.plan_columns[-1]
                matching = [c_idx for c_idx, cell in enumerate(tbl[header_idx]) if last_col in cell]
                if not matching:
                    break
                c_idx = matching[-1]
                data_cells = [tbl[r][c_idx] for r in range(header_idx + 1, len(tbl)) if c_idx < len(tbl[r])]
                real_nums = [c for c in data_cells if re.search(r"\d{2,}", re.sub(r"[,.\s]", "", c))]
                if not real_nums:
                    logger.info("Triage page %d: pruning empty plan column '%s'", pt.page, last_col)
                    pt.plan_columns.pop()
                else:
                    break

    @staticmethod
    def _repair(result: TriageResult, pages: List[PageContent], hint: Optional[str]) -> TriageResult:
        if hint and hint != result.document_type:
            result.reasoning = f"Operator hint {hint} applied (model said {result.document_type}). " + result.reasoning
            result.document_type = hint  # type: ignore[assignment]
        known = {pt.page: pt for pt in result.pages}
        repaired: List[PageTriage] = []
        for p in pages:
            pt = known.get(p.page_no) or PageTriage(page=p.page_no, role="OTHER", is_relevant=True, summary="untagged by triage")
            if pt.continues_page is not None and (pt.continues_page >= pt.page or pt.continues_page < 1):
                pt.continues_page = None
            if pt.role == "BENEFIT_TABLE_CONTINUATION":
                # nearest preceding page that has a header
                nearest = next((prev.page for prev in reversed(repaired) if prev.plan_columns), None)
                if nearest is not None and (pt.continues_page is None or pt.continues_page < nearest or pt.continues_page not in known):
                    pt.continues_page = nearest

            case_topics = {"FCL", "PLAN_DEFINITIONS", "MEMBER_COUNT", "POLICY_PERIOD"} & set(pt.topics)
            if pt.role in ("BENEFIT_TABLE", "BENEFIT_TABLE_CONTINUATION", "CLAIMS_SUMMARY_TABLE", "CLAIMS_DETAIL_TABLE", "CENSUS_TABLE", "PLAN_DEFINITIONS"):
                pt.is_relevant = True
            elif pt.role == "UNDERWRITING_CONDITIONS" and case_topics:
                pt.is_relevant = True  # case-level facts (free cover limit, plan definitions) hide in condition pages
            elif pt.role == "TERMS_BOILERPLATE" and not case_topics:
                pt.is_relevant = False  # disease lists / dismemberment scales never carry target values
            repaired.append(pt)
        TriageService._fix_plan_sequence(repaired, result)
        TriageService._prune_empty_plan_columns(repaired, pages)
        if not any(pt.is_relevant for pt in repaired):
            for pt in repaired:
                pt.is_relevant = True
        result.pages = repaired
        return result

