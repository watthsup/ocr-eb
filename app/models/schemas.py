"""Pydantic schemas: internal pipeline state objects, LLM structured-output models and API payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field, create_model

DocumentType = Literal["BENEFIT_SCHEDULE", "CLAIMS", "CENSUS"]
PageRole = Literal[
    "COVER",
    "BENEFIT_TABLE",
    "BENEFIT_TABLE_CONTINUATION",
    "PLAN_DEFINITIONS",
    "UNDERWRITING_CONDITIONS",
    "CLAIMS_SUMMARY_TABLE",
    "CLAIMS_DETAIL_TABLE",
    "CENSUS_TABLE",
    "TERMS_BOILERPLATE",
    "OTHER",
]


# ============================================================
# Ingestion
# ============================================================
class PageContent(BaseModel):
    page_no: int
    source_file: str
    markdown: str = ""
    tables: List[List[List[str]]] = Field(default_factory=list, description="tables as 2-D cell grids")
    token_estimate: int = 0

    @property
    def table_count(self) -> int:
        return len(self.tables)


# ============================================================
# Stage 2 — Triage ("identify what to hydrate")
# ============================================================
class PageTriage(BaseModel):
    page: int
    role: PageRole
    is_relevant: bool = Field(description="True if this page must be included in the extraction context")
    continues_page: Optional[int] = Field(
        None, description="For continuation tables without their own header: the page whose column header applies"
    )
    plan_columns: List[str] = Field(
        default_factory=list, description="Plan / period column labels exactly as printed in this page's table header"
    )
    topics: List[str] = Field(default_factory=list)
    summary: str = ""


class TriageResult(BaseModel):
    document_type: DocumentType
    reasoning: str
    source_hint: Optional[str] = Field(None, description="Insurer / broker / system that produced the document")
    pages: List[PageTriage]


class ShardSpec(BaseModel):
    shard_id: str
    label: str
    page_nos: List[int]
    shared_page_nos: List[int] = Field(default_factory=list)
    plan_columns: List[str] = Field(default_factory=list)


# ============================================================
# Stage 3 — Extraction (LLM structured output, dynamic field enum)
# ============================================================
class FieldValueOut(BaseModel):
    """Generic field record. `field_code` is constrained at runtime to the CSV catalog via `build_extraction_model`."""

    field_code: str
    value: Optional[str] = Field(
        description="Normalised value as text. Numbers: digits only (no commas/currency). Dates: DD/MM/YYYY in AD. "
        "Flags: Y or N. Not covered / dash / ไม่มี for an amount field: '0'. Unknown or absent: null."
    )
    evidence: Optional[str] = Field(
        None, description="Verbatim label/snippet from the document that this value was read from (as printed, Thai ok)"
    )
    page: Optional[int] = Field(None, description="Page number where the value was read")
    issues: List[str] = Field(default_factory=list)


class RecordGroupOut(BaseModel):
    group_key: str = Field(description="Stable key: plan number as printed (e.g. '001', '3'), policy year index, or member id")
    group_label: Optional[str] = Field(None, description="Human label as printed (e.g. 'แผนที่ 1', 'Sr. M & below (local)')")
    fields: List[FieldValueOut]


class ExtractionOut(BaseModel):
    case_fields: List[FieldValueOut] = Field(description="Fields whose granularity is once per document/case")
    groups: List[RecordGroupOut] = Field(description="One entry per plan / policy year / member found in the context")
    notes: Optional[str] = Field(None, description="Anything ambiguous the reviewer should know")


def build_extraction_model(codes: List[str]) -> Type[ExtractionOut]:
    """Create a strict ExtractionOut variant whose field_code is an enum of the catalog codes for this doc type."""
    literal = Literal[tuple(codes)]  # type: ignore[valid-type]
    FieldValueDyn = create_model("FieldValueDyn", __base__=FieldValueOut, field_code=(literal, ...))
    RecordGroupDyn = create_model("RecordGroupDyn", __base__=RecordGroupOut, fields=(List[FieldValueDyn], ...))
    return create_model(
        "ExtractionDyn",
        __base__=ExtractionOut,
        case_fields=(List[FieldValueDyn], ...),
        groups=(List[RecordGroupDyn], ...),
    )


class GroupValue(BaseModel):
    group_key: str = Field(description="Plan / period key exactly as in `groups`")
    value: Optional[str] = Field(description="Normalised value for this group, '0' for a printed dash, null if the cell is empty")


class MatrixRowOut(BaseModel):
    """One benefit row of the table: a field with one value per plan / period (mirrors the document layout)."""

    field_code: str
    evidence: Optional[str] = Field(None, description="Row label exactly as printed, plus raw cell text when it differs")
    page: Optional[int] = None
    source_row: Optional[str] = Field(
        None, description="Tag of the table row the values were read from, e.g. 'p3.t1.r5' — the pipeline copies that row's printed cells per plan column"
    )
    values: List[GroupValue]


class MatrixGroupOut(BaseModel):
    group_key: str = Field(description="Plan number / period index as printed without the word แผน/Plan (e.g. '1', '001')")
    group_label: Optional[str] = Field(None, description="Header label or plan definition as printed")


class MatrixExtractionOut(BaseModel):
    case_fields: List[FieldValueOut] = Field(description="Scope=case fields, once per document")
    groups: List[MatrixGroupOut] = Field(description="Every plan / period column found in the context")
    rows: List[MatrixRowOut] = Field(description="One row per field; only the catch-all list field may repeat")
    notes: Optional[str] = None

    def to_generic(self) -> "ExtractionOut":
        by_key: Dict[str, RecordGroupOut] = {}
        for g in self.groups:
            by_key.setdefault(g.group_key.strip(), RecordGroupOut(group_key=g.group_key.strip(), group_label=g.group_label, fields=[]))
        for row in self.rows:
            for gv in row.values:
                key = gv.group_key.strip()
                grp = by_key.setdefault(key, RecordGroupOut(group_key=key, group_label=None, fields=[]))
                if gv.value is None:
                    continue
                grp.fields.append(FieldValueOut(field_code=row.field_code, value=gv.value, evidence=row.evidence, page=row.page))
        return ExtractionOut(case_fields=self.case_fields, groups=list(by_key.values()), notes=self.notes)


def build_matrix_extraction_model(codes: List[str]) -> Type[MatrixExtractionOut]:
    literal = Literal[tuple(codes)]  # type: ignore[valid-type]
    FieldValueDyn = create_model("FieldValueDynM", __base__=FieldValueOut, field_code=(literal, ...))
    RowDyn = create_model("MatrixRowDyn", __base__=MatrixRowOut, field_code=(literal, ...))
    return create_model("MatrixExtractionDyn", __base__=MatrixExtractionOut, case_fields=(List[FieldValueDyn], ...), rows=(List[RowDyn], ...))


class ColumnMap(BaseModel):
    column_index: int
    header_text: str
    field_code: Optional[str] = Field(None, description="Catalog field this column maps to, or null if not a target field")


class ColumnMappingOut(BaseModel):
    columns: List[ColumnMap]
    header_row_index: int = Field(description="0-based index of the header row inside the table")
    first_data_row_index: int
    notes: Optional[str] = None


def build_column_mapping_model(codes: List[str]) -> Type[ColumnMappingOut]:
    literal = Optional[Literal[tuple(codes)]]  # type: ignore[valid-type]
    ColumnMapDyn = create_model("ColumnMapDyn", __base__=ColumnMap, field_code=(literal, None))
    return create_model("ColumnMappingDyn", __base__=ColumnMappingOut, columns=(List[ColumnMapDyn], ...))


# ============================================================
# Stage 4 — Normalised result (API facing)
# ============================================================
FieldStatus = Literal["extracted", "not_found", "needs_review"]
FieldVerification = Literal["in_source", "not_in_source", "derived", "edited", "not_checked"]


class FieldResult(BaseModel):
    field_code: str
    name_en: str = ""
    name_th: str = ""
    type: str = "Text"
    scope: str = "group"
    value: Optional[Any] = None
    raw_value: Optional[str] = None
    evidence: Optional[str] = None
    page: Optional[int] = None
    verification: FieldVerification = "not_checked"
    status: FieldStatus = "not_found"
    issues: List[str] = Field(default_factory=list)
    edited: bool = False


class RecordGroup(BaseModel):
    group_key: str
    group_label: Optional[str] = None
    fields: List[FieldResult] = Field(default_factory=list)


class ResultSummary(BaseModel):
    total: int = 0
    extracted: int = 0
    needs_review: int = 0
    not_found: int = 0


class ExtractionResult(BaseModel):
    document_type: DocumentType
    page_count: int
    classification: TriageResult
    shards: List[ShardSpec] = Field(default_factory=list)
    group_noun: str = "Plan"
    case_fields: List[FieldResult] = Field(default_factory=list)
    groups: List[RecordGroup] = Field(default_factory=list)
    catalog: List[dict] = Field(default_factory=list)
    summary: ResultSummary = Field(default_factory=ResultSummary)
    timings_ms: Dict[str, float] = Field(default_factory=dict)
    llm_calls: int = 0
    notes: List[str] = Field(default_factory=list)


# ============================================================
# Jobs / API
# ============================================================
StageState = Literal["pending", "running", "done", "failed", "skipped"]
STAGE_DEFS: List[tuple[str, str]] = [
    ("uploaded", "Uploaded"),
    ("ocr", "OCR & Layout Analysis (Azure)"),
    ("classifying", "Classifying Document"),
    ("extracting", "Extracting Fields"),
    ("normalizing", "Normalizing & Validating"),
    ("ready", "Ready for Review"),
]


class StageStatus(BaseModel):
    key: str
    label: str
    status: StageState = "pending"
    ms: Optional[float] = None


class Job(BaseModel):
    job_id: str
    case_name: str = ""
    filenames: List[str] = Field(default_factory=list)
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stages: List[StageStatus] = Field(default_factory=lambda: [StageStatus(key=k, label=l) for k, l in STAGE_DEFS])
    result: Optional[ExtractionResult] = None

    def set_stage(self, key: str, status: StageState, ms: Optional[float] = None) -> None:
        for st in self.stages:
            if st.key == key:
                st.status = status
                if ms is not None:
                    st.ms = round(ms, 1)


class FieldOverride(BaseModel):
    group_key: Optional[str] = None
    field_code: str
    value: Optional[Any] = None


class FieldOverrideRequest(BaseModel):
    overrides: List[FieldOverride]


class JobCreated(BaseModel):
    job_id: str
