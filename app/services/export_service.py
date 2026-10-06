"""Step 5 — Export: business-ready Excel workbook mirroring example_data/example_user_friendly_output.

Layout (Benefit schedule / Claim history): title block, case-level facts, then a matrix
`Benefit | As printed (Thai) | Field code | <one column per plan / policy year>` with category bands.
Census: one row per member. A "Field inspector" sheet lists every field with status/verification/evidence.
"""

from __future__ import annotations

import io
import re
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.schemas import ExtractionResult, FieldResult, Job

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
BAND_FILL = PatternFill("solid", fgColor="D9E1F2")
REVIEW_FILL = PatternFill("solid", fgColor="FFF3CD")
MISSING_FONT = Font(color="9E9E9E")
WHITE_BOLD = Font(color="FFFFFF", bold=True)
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14)

CATEGORY_RULES: List[tuple[str, str]] = [
    (r"^PLAN_", "Plan"),
    (r"^(BEN_GTL|BEN_GADD|BEN_GTPD|BEN_GCI|BEN_GPA|BEN_GME|BEN_HS_DEATH)", "Life & accident"),
    (r"^(BEN_IPD_|BEN_PRE_HOS|BEN_POST_HOS|BEN_LAB|BEN_SMM|BEN_COPAY_IPD|BEN_HI)", "In-patient"),
    (r"^(BEN_OPD_|BEN_COPAY_OPD)", "Out-patient"),
    (r"^(BEN_DEN|BEN_COPAY_DEN)", "Dental"),
    (r"^BEN_MAT_", "Maternity"),
    (r"^(BEN_VISION|BEN_EXTRA_LIST|BEN_FLAG)", "Other benefits"),
    (r"^(CLM_PERIOD|CLM_START|CLM_END|CLM_CENSUS)", "Period"),
    (r"^CLM_AMT_", "Claim amounts"),
    (r"^CLM_CNT_", "Claim counts"),
    (r"^(CLM_CLAIMANT|CLM_HOSPITAL)", "Claimants & hospitals"),
    (r"^(ICD10|DESCRIPTION|CANCER)", "Diagnoses"),
]
SHEET_NAME = {"BENEFIT_SCHEDULE": "Benefit schedule", "CLAIMS": "Claim history", "CENSUS": "Member census"}


def category_of(code: str) -> str:
    for pattern, name in CATEGORY_RULES:
        if re.match(pattern, code):
            return name
    return "Other"


def _cell_value(f: FieldResult):
    if f.value is None:
        return "—"
    return f.value


def _style_cell(cell, f: Optional[FieldResult]) -> None:
    if f is None:
        return
    if f.status == "not_found":
        cell.font = MISSING_FONT
    elif f.status == "needs_review":
        cell.fill = REVIEW_FILL
    if isinstance(f.value, (int, float)):
        cell.number_format = "#,##0.##"
        cell.alignment = Alignment(horizontal="right")


def _autosize(ws, min_w: int = 8, max_w: int = 48) -> None:
    widths: Dict[int, int] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None:
                widths[c.column] = max(widths.get(c.column, 0), len(str(c.value)))
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = max(min_w, min(max_w, w + 2))


def _title_block(ws, job: Job, result: ExtractionResult) -> int:
    ws["A1"] = f"{job.case_name or job.job_id[:8]} — {SHEET_NAME.get(result.document_type, result.document_type)}"
    ws["A1"].font = TITLE
    ws["A2"] = "Source: " + ", ".join(job.filenames)
    facts = [f"{f.name_en}: {f.value}" for f in result.case_fields if f.value is not None]
    facts.append(f"{result.group_noun}s: {len(result.groups)}")
    facts.append(f"Extracted {result.summary.extracted} · Needs review {result.summary.needs_review} · Not found {result.summary.not_found}")
    ws["A3"] = "   ·   ".join(facts)
    return 5


def _is_extracted(f: Optional[FieldResult]) -> bool:
    if f is None:
        return False
    if f.status in ("extracted", "needs_review"):
        return True
    return f.value is not None and f.value != ""


def _matrix_sheet(ws, job: Job, result: ExtractionResult) -> None:
    row = _title_block(ws, job, result)
    groups = result.groups
    noun = "แผน" if result.document_type == "BENEFIT_SCHEDULE" else result.group_noun
    headers = ["Benefit", "As printed (Thai)", "Field code"] + [
        f"{noun} {g.group_key}" + (f"\n{g.group_label}" if g.group_label and g.group_label != g.group_key else "") for g in groups
    ]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=col, value=h)
        c.fill, c.font = HEADER_FILL, WHITE_BOLD
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center" if col > 3 else "left")
    ws.freeze_panes = ws.cell(row=row + 1, column=4)
    row += 1

    specs = [s for s in result.catalog if s["scope"] == "group"]
    # Only keep rows that have at least one extracted value across groups
    extracted_specs = [
        spec for spec in specs
        if any(_is_extracted(next((f for f in g.fields if f.field_code == spec["field_code"]), None)) for g in groups)
    ]
    active_specs = extracted_specs if extracted_specs else specs

    current_cat = None
    for spec in active_specs:
        code = spec["field_code"]
        cat = category_of(code)
        if cat != current_cat:
            current_cat = cat
            c = ws.cell(row=row, column=1, value=cat)
            c.font = BOLD
            for col in range(1, len(headers) + 1):
                ws.cell(row=row, column=col).fill = BAND_FILL
            row += 1
        per_group = [next((f for f in g.fields if f.field_code == code), None) for g in groups]
        printed = next((f.evidence for f in per_group if f and f.evidence), spec["name_th"])
        ws.cell(row=row, column=1, value=spec["name_en"])
        ws.cell(row=row, column=2, value=printed)
        ws.cell(row=row, column=3, value=code).font = Font(name="Consolas", size=9)
        for j, f in enumerate(per_group, start=4):
            cell = ws.cell(row=row, column=j, value=_cell_value(f) if f else "—")
            _style_cell(cell, f)
        row += 1
    _autosize(ws)
    ws.column_dimensions["B"].width = 44


def _census_sheet(ws, job: Job, result: ExtractionResult) -> None:
    row = _title_block(ws, job, result)
    specs = [s for s in result.catalog if s["scope"] == "group"]
    extracted_specs = [
        s for s in specs
        if any(_is_extracted(next((f for f in g.fields if f.field_code == s["field_code"]), None)) for g in result.groups)
    ]
    active_specs = extracted_specs if extracted_specs else specs
    headers = ["#", "Member"] + [f"{s['name_en']}\n{s['field_code']}" for s in active_specs]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=col, value=h)
        c.fill, c.font = HEADER_FILL, WHITE_BOLD
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = ws.cell(row=row + 1, column=3)
    row += 1
    for i, g in enumerate(result.groups, start=1):
        ws.cell(row=row, column=1, value=i)
        ws.cell(row=row, column=2, value=g.group_key)
        by_code = {f.field_code: f for f in g.fields}
        for j, s in enumerate(active_specs, start=3):
            f = by_code.get(s["field_code"])
            cell = ws.cell(row=row, column=j, value=_cell_value(f) if f else "—")
            _style_cell(cell, f)
        row += 1
    _autosize(ws)


def _inspector_sheet(ws, result: ExtractionResult) -> None:
    headers = ["Group", "Field code", "Field (EN)", "ชื่อฟิลด์ (TH)", "Value", "Raw", "Evidence (as printed)", "Page", "Status", "Issues"]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill, c.font = HEADER_FILL, WHITE_BOLD
    ws.freeze_panes = "A2"
    row = 2

    def write(group: str, f: FieldResult) -> None:
        nonlocal row
        values = [group, f.field_code, f.name_en, f.name_th, _cell_value(f), f.raw_value, f.evidence, f.page,
                  f.status, "; ".join(f.issues)]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            if col == 5:
                _style_cell(cell, f)
        row += 1

    has_extracted = any(_is_extracted(f) for f in result.case_fields) or any(
        _is_extracted(f) for g in result.groups for f in g.fields
    )

    for f in result.case_fields:
        if not has_extracted or _is_extracted(f):
            write("Case", f)
    for g in result.groups:
        for f in g.fields:
            if not has_extracted or _is_extracted(f):
                write(g.group_key, f)
    _autosize(ws, max_w=60)


def _run_info_sheet(ws, job: Job, result: ExtractionResult) -> None:
    rows = [
        ("Job", job.job_id), ("Case", job.case_name), ("Files", ", ".join(job.filenames)),
        ("Document type", result.document_type),
        ("Reasoning", result.classification.reasoning), ("Pages", result.page_count),
        ("Pages hydrated", ", ".join(str(p.page) for p in result.classification.pages if p.is_relevant)),
        ("Shards", "; ".join(f"{s.shard_id}: pages {s.page_nos} (+shared {s.shared_page_nos})" for s in result.shards)),
        ("LLM calls", result.llm_calls), ("Timings (ms)", ", ".join(f"{k}={v}" for k, v in result.timings_ms.items())),
        ("Notes", " | ".join(result.notes)),
    ]
    for i, (k, v) in enumerate(rows, start=1):
        ws.cell(row=i, column=1, value=k).font = BOLD
        ws.cell(row=i, column=2, value=v)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 120


class ExportService:
    def build_workbook(self, job: Job) -> bytes:
        if job.result is None:
            raise ValueError("Job has no result to export")
        result = job.result
        wb = Workbook()
        ws = wb.active
        ws.title = SHEET_NAME.get(result.document_type, "Extraction")
        if result.document_type == "CENSUS":
            _census_sheet(ws, job, result)
        else:
            _matrix_sheet(ws, job, result)
        _inspector_sheet(wb.create_sheet("Field inspector"), result)
        _run_info_sheet(wb.create_sheet("Run info"), job, result)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
