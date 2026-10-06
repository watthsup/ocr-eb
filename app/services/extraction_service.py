"""Step 3 — Extraction: shard planning, context hydration, parallel structured LLM calls, merge.

Sharding axis is chosen per document type:
* BENEFIT_SCHEDULE — by *plan-column section* (header page + its continuation pages) with shared
  case-level pages (plan definitions / FCL) copied into every shard. Never by raw page, because
  continuation pages have no header of their own.
* CLAIMS / CENSUS — rows are independent, so sequential page chunks with the header page carried over.
* CENSUS with a real table — LLM maps columns once, pandas-style row parsing does the rest.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from app.clients.llm_client import LLMClient
from app.core.config import settings
from app.models.schemas import (
    ExtractionOut,
    FieldValueOut,
    GroupValue,
    PageContent,
    PageTriage,
    RecordGroupOut,
    ShardSpec,
    TriageResult,
    build_column_mapping_model,
    build_extraction_model,
    build_matrix_extraction_model,
)
from app.services.field_catalog import FieldCatalog, get_catalog
from app.services.prompt_loader import render

logger = logging.getLogger(__name__)

PROMPT_BY_TYPE = {"BENEFIT_SCHEDULE": "benefit_schedule", "CLAIMS": "claims", "CENSUS": "census"}
MATRIX_TYPES = {"BENEFIT_SCHEDULE", "CLAIMS"}  # table-shaped output: one row per field, one value per plan/period
TABLE_ROLES = {"BENEFIT_TABLE", "BENEFIT_TABLE_CONTINUATION", "CLAIMS_SUMMARY_TABLE", "CLAIMS_DETAIL_TABLE", "CENSUS_TABLE"}
HTML_TABLE_RE = re.compile(r"<table>.*?</table>", re.DOTALL | re.IGNORECASE)


# ----------------------------------------------------------------------------
# Context hydration helpers
# ----------------------------------------------------------------------------
def grid_to_pipe_table(grid: List[List[str]], tag_prefix: Optional[str] = None) -> str:
    """Pipe table; with `tag_prefix` (e.g. 'p3.t1') every row is prefixed by a `[p3.t1.r5]` tag the model can reference."""
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    rows = [r + [""] * (width - len(r)) for r in grid]

    def render(i: int, r: List[str]) -> str:
        cells = [c.replace("|", "/") for c in r]
        if tag_prefix:
            cells[0] = f"[{tag_prefix}.r{i}] {cells[0]}"
        return "| " + " | ".join(cells) + " |"

    lines = [render(0, rows[0]), "|" + "---|" * width] + [render(i, r) for i, r in enumerate(rows[1:], start=1)]
    return "\n".join(lines)


def compact_markdown(page: PageContent, tag_rows: bool = False) -> str:
    """Replace Azure DI's verbose HTML tables with pipe tables (≈40% fewer tokens), drop page-break comments."""
    md = page.markdown
    html_tables = HTML_TABLE_RE.findall(md)
    if html_tables and len(html_tables) == len(page.tables):
        for t, (html, grid) in enumerate(zip(html_tables, page.tables), start=1):
            md = md.replace(html, grid_to_pipe_table(grid, f"p{page.page_no}.t{t}" if tag_rows else None), 1)
    elif page.tables and tag_rows:
        # spreadsheet pages (pandas markdown preview) or DI pages without HTML tables: render the grids themselves, tagged
        heading = md.splitlines()[0] if md.startswith("#") else ""
        rendered = []
        for t, grid in enumerate(page.tables, start=1):
            rendered.append(grid_to_pipe_table(grid[:400], f"p{page.page_no}.t{t}") + (f"\n... {len(grid) - 400} more rows omitted" if len(grid) > 400 else ""))
        md = (heading + "\n\n" if heading else "") + "\n\n".join(rendered)
    md = re.sub(r"<!--\s*PageBreak\s*-->", "", md)
    md = re.sub(r"<!--\s*PageNumber=\"?[^>]*-->", "", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


ROW_TAG_RE = re.compile(r"p(\d+)\.t(\d+)\.r(\d+)")


def _digits(text: Optional[str]) -> str:
    return re.sub(r"\D", "", text or "")


def ground_rows(out, pages: List[PageContent], triage: TriageResult, groundable: Optional[set] = None) -> int:
    """LLM picks the row, code copies the printed cells: overwrite `values` of rows that cite a `source_row` tag with the
    OCR grid cells mapped by plan-column position. Eliminates column shift and digit transcription errors.

    Conservative: only fields in `groundable` (amount-like), and only when at least one of the model's own values already
    equals a cell of that row — proof that the model read the cells, not a limit printed inside the label."""
    by_no = {p.page_no: p for p in pages}
    tri = {pt.page: pt for pt in triage.pages}
    key_of = {normalize_group_key(g.group_key): g.group_key for g in out.groups}
    grounded = 0
    for row in out.rows:
        m = ROW_TAG_RE.search(row.source_row or "")
        if not m:
            continue
        page_no, t, r = (int(x) for x in m.groups())
        page = by_no.get(page_no)
        if page is None or t < 1 or t > len(page.tables) or r >= len(page.tables[t - 1]):
            continue
        pt = tri.get(page_no)
        cols = (pt.plan_columns if pt and pt.plan_columns else (tri[pt.continues_page].plan_columns if pt and pt.continues_page in tri else [])) if pt else []
        cells = page.tables[t - 1][r]
        label_idx = next((i for i, c in enumerate(cells) if c.strip()), 0)
        value_cells = cells[label_idx + 1:]
        if not cols or len(value_cells) != len(cols):
            continue
        if not any(re.search(r"\d", c) or c.strip() in {"-", "–", "—"} for c in value_cells):
            continue  # nothing printed — keep the model's reading (e.g. limits derived from the label)
        if groundable is not None and row.field_code not in groundable:
            continue
        cell_digits = {_digits(c) for c in value_cells if _digits(c)}
        model_digits = {_digits(v.value) for v in row.values if _digits(v.value)}
        if not (cell_digits & model_digits):
            continue  # the model's numbers do not come from this row's cells (companion limit read from the label)
        new_values = []
        for col, cell in zip(cols, value_cells):
            gk = key_of.get(normalize_group_key(col))
            if gk is None:
                continue
            cell = cell.strip()
            new_values.append(GroupValue(group_key=gk, value=(cell if cell else None)))
        if len(new_values) == len(cols):
            row.values = new_values
            row.page = page_no
            grounded += 1
    return grounded


def normalize_group_key(key: str) -> str:
    digits = re.findall(r"\d+", key or "")
    if digits and len(digits) == 1:
        return str(int(digits[0]))
    return (key or "").strip().lower()


class ExtractionService:
    def __init__(self, llm: Optional[LLMClient] = None, catalog: Optional[FieldCatalog] = None):
        self.llm = llm or LLMClient()
        self.catalog = catalog or get_catalog()

    # ------------------------------------------------------------------
    # Shard planning
    # ------------------------------------------------------------------
    def plan_shards(self, doc_type: str, pages: List[PageContent], triage: TriageResult) -> List[ShardSpec]:
        by_no: Dict[int, PageContent] = {p.page_no: p for p in pages}
        relevant = [pt for pt in triage.pages if pt.is_relevant and pt.page in by_no]
        if not relevant:
            relevant = list(triage.pages)
        total_tokens = sum(by_no[pt.page].token_estimate for pt in relevant)
        strategy = settings.SHARD_STRATEGY

        if doc_type == "BENEFIT_SCHEDULE":
            sections, shared = self._benefit_sections(relevant)
            if strategy == "single" or len(sections) <= 1 or (strategy == "auto" and total_tokens <= settings.SINGLE_SHARD_TOKEN_LIMIT):
                return [ShardSpec(shard_id="S1", label="whole document", page_nos=sorted(pt.page for pt in relevant),
                                  plan_columns=self._all_plan_columns(relevant))]
            shards = []
            for i, (cols, page_nos) in enumerate(sections.items(), start=1):
                shards.append(ShardSpec(shard_id=f"S{i}", label=f"plans {', '.join(cols) if cols else 'unlabelled'}",
                                        page_nos=sorted(page_nos), shared_page_nos=sorted(shared), plan_columns=list(cols)))
            return shards

        # CLAIMS / CENSUS: sequential chunks under the token budget, header page carried over
        ordered = sorted(relevant, key=lambda pt: pt.page)
        header_page = next((pt.page for pt in ordered if pt.role in TABLE_ROLES), ordered[0].page)
        chunks: List[List[int]] = [[]]
        used = 0
        for pt in ordered:
            tok = by_no[pt.page].token_estimate
            if chunks[-1] and used + tok > settings.SHARD_TOKEN_BUDGET and strategy != "single":
                chunks.append([])
                used = 0
            chunks[-1].append(pt.page)
            used += tok
        shards = []
        for i, chunk in enumerate(chunks, start=1):
            shared = [header_page] if (i > 1 and header_page not in chunk) else []
            shards.append(ShardSpec(shard_id=f"S{i}", label=f"pages {chunk[0]}–{chunk[-1]}", page_nos=chunk, shared_page_nos=shared))
        return shards

    @staticmethod
    def _all_plan_columns(pts: List[PageTriage]) -> List[str]:
        seen: "OrderedDict[str, None]" = OrderedDict()
        for pt in pts:
            for c in pt.plan_columns:
                seen.setdefault(c, None)
        return list(seen)

    @staticmethod
    def _benefit_sections(relevant: List[PageTriage]) -> Tuple["OrderedDict[Tuple[str, ...], List[int]]", List[int]]:
        """Group table pages by their plan-column header; attach continuation pages to the header they continue."""
        sections: "OrderedDict[Tuple[str, ...], List[int]]" = OrderedDict()
        page_section: Dict[int, Tuple[str, ...]] = {}
        shared: List[int] = []
        ordered = sorted(relevant, key=lambda pt: pt.page)
        for pt in ordered:
            if pt.role == "BENEFIT_TABLE" or (pt.plan_columns and pt.role not in ("PLAN_DEFINITIONS", "UNDERWRITING_CONDITIONS", "COVER")):
                key = tuple(pt.plan_columns) or (f"page-{pt.page}",)
                sections.setdefault(key, []).append(pt.page)
                page_section[pt.page] = key
            elif pt.role == "BENEFIT_TABLE_CONTINUATION" or pt.continues_page is not None:
                parent = pt.continues_page
                key = page_section.get(parent) if parent else None
                if key is None:  # nearest preceding section
                    key = next(iter(reversed(sections)), None) if sections else None
                if key is None:
                    key = (f"page-{pt.page}",)
                sections.setdefault(key, []).append(pt.page)
                page_section[pt.page] = key
            else:
                shared.append(pt.page)
        return sections, shared

    # ------------------------------------------------------------------
    # Context construction
    # ------------------------------------------------------------------
    def build_context(self, shard: ShardSpec, pages: List[PageContent], triage: TriageResult) -> str:
        by_no = {p.page_no: p for p in pages}
        tri = {pt.page: pt for pt in triage.pages}
        blocks: List[str] = []

        def header(pt: PageTriage, shared: bool) -> str:
            parts = [f"PAGE {pt.page}", pt.role]
            if pt.role == "BENEFIT_TABLE_CONTINUATION" or (pt.continues_page and not pt.plan_columns):
                parent = tri.get(pt.continues_page) if pt.continues_page else None
                cols = parent.plan_columns if parent else []
                parts[1] = f"{pt.role} of page {pt.continues_page}"
                if cols:
                    mapping = "; ".join(f"value column {i} → {c}" for i, c in enumerate(cols, start=1))
                    parts.append(f"inherited columns: {mapping}")
                else:
                    parts.append("inherited columns: same order as the page it continues")
            elif pt.plan_columns:
                parts.append("plan columns: " + ", ".join(pt.plan_columns))
            if shared:
                parts.append("shared case-level context")
            if pt.topics:
                parts.append("topics: " + ", ".join(pt.topics))
            return "[" + " | ".join(parts) + "]"

        for no in shard.shared_page_nos:
            if no in by_no:
                pt = tri.get(no) or PageTriage(page=no, role="OTHER", is_relevant=True)
                blocks.append(header(pt, shared=True) + "\n" + compact_markdown(by_no[no], tag_rows=True))
        for no in shard.page_nos:
            if no in by_no:
                pt = tri.get(no) or PageTriage(page=no, role="OTHER", is_relevant=True)
                blocks.append(header(pt, shared=False) + "\n" + compact_markdown(by_no[no], tag_rows=True))
        return "\n\n".join(blocks)

    def system_prompt(self, doc_type: str) -> str:
        block = self.catalog.prompt_block(doc_type)
        overflow = self.catalog.overflow_field(doc_type) or "(no catch-all field in catalog — put unmapped rows in notes)"
        return render(PROMPT_BY_TYPE[doc_type], FIELD_CATALOG=block, OVERFLOW_FIELD=overflow)

    # ------------------------------------------------------------------
    # LLM extraction
    # ------------------------------------------------------------------
    def _output_model(self, doc_type: str):
        codes = self.catalog.codes(doc_type)
        return build_matrix_extraction_model(codes) if doc_type in MATRIX_TYPES else build_extraction_model(codes)

    async def _call(self, doc_type: str, system: str, user: str, label: str, effort: Optional[str] = None,
                    pages: Optional[List[PageContent]] = None, triage: Optional[TriageResult] = None) -> ExtractionOut:
        """Structured call with graceful degradation: a length blow-up retries at lower reasoning effort."""
        model = self._output_model(doc_type)
        actual_effort = effort or settings.OPENAI_REASONING_EFFORT or "low"
        try:
            out = await self.llm.structured(system, user, model, reasoning_effort=actual_effort, label=label)
        except Exception as exc:
            lower = "minimal" if actual_effort in ("low", "minimal") else "low"
            logger.warning("%s failed (%s: %s) — retrying with reasoning_effort=%s", label, type(exc).__name__, str(exc)[:160], lower)
            out = await self.llm.structured(system, user, model, reasoning_effort=lower, label=f"{label}:retry")
        if hasattr(out, "to_generic"):
            if pages is not None and triage is not None:
                groundable = {sp.field_code for sp in self.catalog.for_doc_type(doc_type)
                              if (sp.type == "Number" and not sp.multi_value) or (sp.type == "Text" and sp.allowed_values)}
                grounded = ground_rows(out, pages, triage, groundable)
                if grounded:
                    logger.info("%s: %d row(s) grounded to OCR table cells", label, grounded)
            return out.to_generic()
        return out

    async def extract_shard(self, doc_type: str, shard: ShardSpec, pages: List[PageContent], triage: TriageResult) -> ExtractionOut:
        context = self.build_context(shard, pages, triage)
        user = (f"# Document context — shard {shard.shard_id} ({shard.label})\n"
                f"Document type: {doc_type}. Source: {triage.source_hint or 'unknown'}.\n"
                + (f"Plan columns expected in this shard: {', '.join(shard.plan_columns)}\n" if shard.plan_columns else "")
                + "\n" + context)
        logger.info("Extracting shard %s: pages=%s shared=%s ≈%d tokens", shard.shard_id, shard.page_nos, shard.shared_page_nos,
                    sum(p.token_estimate for p in pages if p.page_no in set(shard.page_nos) | set(shard.shared_page_nos)))
        return await self._call(doc_type, self.system_prompt(doc_type), user, label=f"extract:{shard.shard_id}", pages=pages, triage=triage)

    async def extract_all(self, doc_type: str, shards: List[ShardSpec], pages: List[PageContent], triage: TriageResult) -> List[ExtractionOut]:
        sem = asyncio.Semaphore(settings.MAX_PARALLEL_SHARDS)

        async def run(shard: ShardSpec) -> ExtractionOut:
            async with sem:
                return await self.extract_shard(doc_type, shard, pages, triage)

        return list(await asyncio.gather(*[run(s) for s in shards]))

    # ------------------------------------------------------------------
    # Merge (plans are disjoint across shards; case fields: keep the most confident)
    # ------------------------------------------------------------------
    def merge(self, results: List[ExtractionOut]) -> ExtractionOut:
        multi = {s.field_code for s in self.catalog.specs if s.multi_value}
        return self._merge(results, multi)

    @staticmethod
    def _merge(results: List[ExtractionOut], multi_codes: set = frozenset()) -> ExtractionOut:
        groups: "OrderedDict[str, RecordGroupOut]" = OrderedDict()
        case: Dict[str, FieldValueOut] = {}
        notes: List[str] = []
        for res in results:
            for f in res.case_fields:
                if f.field_code not in case:
                    case[f.field_code] = f
                else:
                    cur = case[f.field_code]
                    if not cur.value and f.value:
                        case[f.field_code] = f
                    elif cur.value and f.value and cur.value != f.value:
                        cur.issues.append(f"shard conflict: '{cur.value}' vs '{f.value}'")
            for g in res.groups:
                key = normalize_group_key(g.group_key)
                if key not in groups:
                    groups[key] = RecordGroupOut(group_key=g.group_key, group_label=g.group_label, fields=[])
                target = groups[key]
                if not target.group_label and g.group_label:
                    target.group_label = g.group_label
                existing = {f.field_code: f for f in target.fields if f.field_code not in multi_codes}
                multi_items = [f for f in target.fields if f.field_code in multi_codes]
                for f in g.fields:
                    if f.field_code in multi_codes:
                        if f.value and f.value not in {m.value for m in multi_items}:
                            multi_items.append(f)
                        continue
                    cur = existing.get(f.field_code)
                    if cur is None:
                        existing[f.field_code] = f
                    elif not cur.value and f.value:
                        existing[f.field_code] = f
                    elif cur.value and f.value and cur.value != f.value:
                        cur.issues.append(f"shard conflict: '{cur.value}' vs '{f.value}'")
                target.fields = list(existing.values()) + multi_items
            if res.notes:
                notes.append(res.notes)
        return ExtractionOut(case_fields=list(case.values()), groups=list(groups.values()), notes=" | ".join(notes) or None)

    # ------------------------------------------------------------------
    # Recall guard: deterministic coverage audit + targeted gap-fill call
    # ------------------------------------------------------------------
    def audit_coverage(self, pages: List[PageContent], triage: TriageResult, extraction: ExtractionOut) -> List[Dict]:
        """Return numeric table rows (on hydrated pages) whose label is not referenced by any extracted evidence."""
        norm = lambda t: re.sub(r"[^0-9a-zA-Z\u0E00-\u0E7F]", "", (t or "").lower())
        blob = norm(" ".join((f.evidence or "") + " " + (f.value or "") for g in extraction.groups for f in g.fields)
                    + " ".join((f.evidence or "") + " " + (f.value or "") for f in extraction.case_fields))
        tri = {pt.page: pt for pt in triage.pages}
        unmapped: List[Dict] = []
        for p in pages:
            pt = tri.get(p.page_no)
            if pt is None or not pt.is_relevant:
                continue
            cols = pt.plan_columns or (tri[pt.continues_page].plan_columns if pt.continues_page in tri else [])
            for ti, grid in enumerate(p.tables, start=1):
                for ri, row in enumerate(grid):
                    label = next((c for c in row if c.strip()), "")
                    cells = [c.strip() for c in row[1:]] if row and row[0].strip() else [c.strip() for c in row if c.strip() and c != label]
                    numeric = [c for c in cells if re.search(r"\d{2,}", c) or re.search(r"\d\s*[:/]\s*\d", c)]
                    header_like = sum(bool(re.match(r"\s*(แผน|plan|ปีที่|year)", c, re.I)) for c in numeric) >= max(1, len(numeric) // 2)
                    if not numeric or len(norm(label)) < 4 or header_like:
                        continue
                    key = norm(label)[:16]
                    if key in blob or norm(label)[-16:] in blob:
                        continue
                    unmapped.append({"page": p.page_no, "label": label, "cells": cells, "plan_columns": cols, "tag": f"p{p.page_no}.t{ti}.r{ri}"})
        return unmapped

    def keyword_candidates(self, doc_type: str, label: str) -> List[str]:
        """Catalog fields whose TH name or a keyword (≥ 6 chars) appears verbatim in the row label — a hint, not a decision."""
        norm = lambda t: re.sub(r"[^0-9a-zA-Z\u0E00-\u0E7F]", "", (t or "").lower())
        nl = norm(label)
        hits = []
        for sp in self.catalog.for_doc_type(doc_type):
            terms = [re.sub(r"\(.*?\)", "", t) for t in [sp.name_th] + sp.keywords]  # parentheses are explanatory
            if any(len(norm(t)) >= 6 and norm(t) in nl for t in terms):
                hits.append(sp.field_code)
        return hits[:3]

    async def gap_fill(self, doc_type: str, unmapped: List[Dict], triage: TriageResult, pages: Optional[List[PageContent]] = None) -> ExtractionOut:
        overflow = self.catalog.overflow_field(doc_type) or "notes"
        system = render("gap_fill", FIELD_CATALOG=self.catalog.prompt_block(doc_type), OVERFLOW_FIELD=overflow)
        lines = []
        for u in unmapped:
            cols = u["plan_columns"]
            cells = " | ".join(f"{cols[i] if i < len(cols) else f'col{i+1}'} = {c}" for i, c in enumerate(u["cells"]))
            cands = self.keyword_candidates(doc_type, u["label"])
            hint = f" | keyword match → {', '.join(cands)}" if cands else ""
            lines.append(f"- [{u.get('tag', 'p' + str(u['page']))}] page {u['page']} | row label: {u['label']} | {cells}{hint}")
        user = f"Document type: {doc_type}. Source: {triage.source_hint or 'unknown'}.\n\n# Unmapped rows ({len(unmapped)})\n" + "\n".join(lines)
        return await self._call(doc_type, system, user, label="gap-fill", effort="low", pages=pages, triage=triage)

    # ------------------------------------------------------------------
    # CENSUS tabular fast path: map columns once, parse rows deterministically
    # ------------------------------------------------------------------
    async def extract_census_tabular(self, pages: List[PageContent], triage: TriageResult) -> Optional[ExtractionOut]:
        relevant = {pt.page for pt in triage.pages if pt.is_relevant}
        tables: List[Tuple[int, List[List[str]]]] = [(p.page_no, t) for p in pages if p.page_no in relevant for t in p.tables if len(t) >= 3]
        if not tables:
            return None
        # header table = widest table on the earliest page
        first_page = min(pg for pg, _ in tables)
        header_grid = max((t for pg, t in tables if pg == first_page), key=lambda t: len(t[0]))
        width = len(header_grid[0])
        preview = grid_to_pipe_table([[f"[{i}] {c}" for i, c in enumerate(r)] for r in header_grid[:6]])
        codes = self.catalog.codes("CENSUS")
        model = build_column_mapping_model(codes)
        block = self.catalog.prompt_block("CENSUS", scope="group")
        mapping = await self.llm.structured(render("census_column_mapping", FIELD_CATALOG=block),
                                            f"Table preview (first rows, cells prefixed with [column index]):\n\n{preview}",
                                            model, reasoning_effort="low", label="census:column-map")
        col_map = {c.column_index: c.field_code for c in mapping.columns if c.field_code}
        if "CEN_MEMBER_ID" not in col_map.values():
            logger.info("Census column mapping found no member id column — falling back to LLM extraction")
            return None
        header_texts = {c.column_index: c.header_text.strip().lower() for c in mapping.columns}
        id_col = next(i for i, code in col_map.items() if code == "CEN_MEMBER_ID")

        groups: List[RecordGroupOut] = []
        for pg, grid in sorted(tables, key=lambda x: x[0]):
            if len(grid[0]) != width:
                continue
            start = mapping.first_data_row_index if pg == first_page else 0
            for row in grid[start:]:
                row = row + [""] * (width - len(row))
                member_id = row[id_col].strip() if id_col < len(row) else ""
                if not member_id or member_id.lower() in header_texts.values() or member_id.lower() in {"total", "รวม"}:
                    continue
                fields = [FieldValueOut(field_code=code, value=row[i].strip() or None, evidence=row[i].strip() or None, page=pg)
                          for i, code in col_map.items() if i < len(row) and row[i].strip()]
                groups.append(RecordGroupOut(group_key=member_id, group_label=None, fields=fields))
        if not groups:
            return None
        note = f"Census parsed via column mapping ({len(col_map)} mapped columns): " + ", ".join(f"[{i}]→{c}" for i, c in sorted(col_map.items()))
        if mapping.notes:
            note += f" | {mapping.notes}"
        return ExtractionOut(case_fields=[], groups=groups, notes=note)
