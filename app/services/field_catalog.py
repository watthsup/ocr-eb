"""Dynamic target-field catalog loaded from the BA-owned CSV.

The CSV is the single source of truth for *what* to extract. Everything downstream
(LLM prompt blocks, the structured-output enum of allowed field codes, type coercion,
export layout) is derived from it at runtime, so BAs can add/rename fields with zero
code changes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

DocumentType = Literal["BENEFIT_SCHEDULE", "CLAIMS", "CENSUS"]
DOC_GROUP_TO_TYPE: Dict[str, str] = {
    "claim history": "CLAIMS",
    "existing benefit": "BENEFIT_SCHEDULE",
    "census": "CENSUS",
}
GROUP_NOUN: Dict[str, str] = {"BENEFIT_SCHEDULE": "Plan", "CLAIMS": "Policy year", "CENSUS": "Member"}
FIELD_TYPES = ("Number", "Text", "Date", "Flag", "Enum")


@dataclass
class FieldSpec:
    no: int
    doc_type: str
    field_code: str
    name_en: str
    name_th: str
    keywords: List[str]
    source_document: str
    granularity: str
    type: str
    example: str
    validation: str
    scope: str  # "case" (once per document) | "group" (per plan / policy year / member)
    allowed_values: Optional[List[str]] = None
    enum_aliases: Dict[str, str] = field(default_factory=dict)  # normalized alias -> canonical
    multi_value: bool = False

    def to_public(self) -> dict:
        return {
            "field_code": self.field_code,
            "name_en": self.name_en,
            "name_th": self.name_th,
            "keywords": self.keywords,
            "type": self.type,
            "granularity": self.granularity,
            "scope": self.scope,
            "allowed_values": self.allowed_values,
            "validation": self.validation,
            "example": self.example,
            "source_document": self.source_document,
        }


def _clean_code(raw: str) -> str:
    """Repair spreadsheet artefacts such as `CLM_END+C4:F13` -> `CLM_END`."""
    code = raw.strip().split("+")[0].strip()
    code = re.sub(r"[^A-Za-z0-9_<>]", "", code)
    return code


def _parse_allowed(validation: str, type_: str) -> tuple[Optional[List[str]], Dict[str, str]]:
    """Parse 'A | B | C' or 'E = Employee | S = Spouse' into canonical values + aliases."""
    if "|" not in validation:
        return None, {}
    values: List[str] = []
    aliases: Dict[str, str] = {}
    for part in validation.split("|"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            canonical, label = [p.strip() for p in part.split("=", 1)]
            values.append(canonical)
            aliases[label.lower()] = canonical
            aliases[canonical.lower()] = canonical
        else:
            # strip explanatory parentheses e.g. "New (Requested)" -> canonical "New (Requested)", alias "new"
            values.append(part)
            aliases[part.lower()] = part
            base = re.sub(r"\(.*?\)", "", part).strip().lower()
            if base:
                aliases[base] = part
    return (values or None), aliases


def _scope_from_granularity(granularity: str) -> str:
    g = granularity.lower()
    if "1 per case" in g or "per case" in g:
        return "case"
    return "group"


class FieldCatalog:
    def __init__(self, specs: List[FieldSpec], version: str, source: str):
        self.specs = specs
        self.version = version
        self.source = source
        self._by_code: Dict[str, FieldSpec] = {s.field_code: s for s in specs}

    # ---------- loading ----------
    @classmethod
    def from_csv_text(cls, text: str, source: str = "<memory>") -> "FieldCatalog":
        reader = csv.DictReader(io.StringIO(text))
        specs: List[FieldSpec] = []
        for row in reader:
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            doc_group = row.get("Doc Group", "").lower()
            doc_type = DOC_GROUP_TO_TYPE.get(doc_group)
            code = _clean_code(row.get("Field Code", ""))
            if not doc_type or not code:
                continue
            type_ = row.get("Type", "Text").strip().title()
            if type_ not in FIELD_TYPES:
                type_ = "Text"
            validation = row.get("Allowed Values / Validation", "")
            allowed, aliases = _parse_allowed(validation, type_)
            keywords = [k.strip() for k in re.split(r"[;,]", row.get("Other keyword", "")) if k.strip()]
            granularity = row.get("Granularity / Repeat", "")
            specs.append(
                FieldSpec(
                    no=int(row.get("No") or len(specs) + 1),
                    doc_type=doc_type,
                    field_code=code,
                    name_en=row.get("Field Name (EN)", "").rstrip(" -"),
                    name_th=row.get("ชื่อฟิลด์ (TH)", ""),
                    keywords=keywords,
                    source_document=row.get("Source Document", ""),
                    granularity=granularity,
                    type=type_,
                    example=row.get("Example", ""),
                    validation=validation,
                    scope=_scope_from_granularity(granularity),
                    allowed_values=allowed,
                    enum_aliases=aliases,
                    multi_value="multi" in granularity.lower(),
                )
            )
        specs = cls._expand_templates(specs)
        version = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
        logger.info("Loaded field catalog v%s with %d fields from %s", version, len(specs), source)
        return cls(specs, version=version, source=source)

    @classmethod
    def from_csv_path(cls, path: str) -> "FieldCatalog":
        with open(path, "r", encoding="utf-8-sig") as fh:
            return cls.from_csv_text(fh.read(), source=path)

    @staticmethod
    def _expand_templates(specs: List[FieldSpec]) -> List[FieldSpec]:
        """`CLM_CNT_<BEN>` means one claim-count field per claim-amount benefit -> materialise them."""
        out: List[FieldSpec] = []
        for s in specs:
            if "<BEN>" not in s.field_code:
                out.append(s)
                continue
            prefix = s.field_code.split("<BEN>")[0]  # e.g. CLM_CNT_
            for amt in specs:
                if amt.doc_type == s.doc_type and amt.field_code.startswith("CLM_AMT_"):
                    suffix = amt.field_code[len("CLM_AMT_"):]
                    label = amt.name_en.replace("Claim amount", "Claim count").strip(" -")
                    out.append(
                        FieldSpec(
                            no=s.no, doc_type=s.doc_type, field_code=f"{prefix}{suffix}",
                            name_en=label or f"Claim count - {suffix}",
                            name_th=f"จำนวนครั้งเคลม {suffix}", keywords=amt.keywords,
                            source_document=s.source_document, granularity=s.granularity, type="Number",
                            example=s.example, validation=s.validation, scope=s.scope,
                        )
                    )
        # de-duplicate codes keeping first occurrence
        seen: set = set()
        deduped: List[FieldSpec] = []
        for s in out:
            if s.field_code in seen:
                continue
            seen.add(s.field_code)
            deduped.append(s)
        return deduped

    # ---------- queries ----------
    def for_doc_type(self, doc_type: str) -> List[FieldSpec]:
        return [s for s in self.specs if s.doc_type == doc_type]

    def codes(self, doc_type: str) -> List[str]:
        return [s.field_code for s in self.for_doc_type(doc_type)]

    def get(self, code: str) -> Optional[FieldSpec]:
        return self._by_code.get(code)

    def overflow_field(self, doc_type: str) -> Optional[str]:
        """The catch-all multi-row Text field for unmapped rows (e.g. BEN_EXTRA_LIST), derived from the CSV granularity."""
        return next((s.field_code for s in self.for_doc_type(doc_type) if s.multi_value and s.type == "Text"), None)

    def doc_types(self) -> List[str]:
        return sorted({s.doc_type for s in self.specs})

    def public(self) -> dict:
        return {
            "version": self.version,
            "source": self.source,
            "doc_types": {dt: [s.to_public() for s in self.for_doc_type(dt)] for dt in self.doc_types()},
        }

    # ---------- prompt context block ----------
    def prompt_block(self, doc_type: str, scope: Optional[str] = None) -> str:
        """Compact markdown table of target fields — this is the CSV-driven context injected into prompts."""
        rows = [s for s in self.for_doc_type(doc_type) if scope is None or s.scope == scope]
        lines = ["| field_code | scope | name (EN) | ชื่อฟิลด์ (TH) | also appears as / keywords | type | rule | example |",
                 "|---|---|---|---|---|---|---|---|"]
        for s in rows:
            kw = "; ".join(s.keywords) if s.keywords else "-"
            rule = s.validation or "-"
            lines.append(f"| {s.field_code} | {s.scope} | {s.name_en} | {s.name_th} | {kw} | {s.type} | {rule} | {s.example or '-'} |")
        return "\n".join(lines)


_catalog: Optional[FieldCatalog] = None


def get_catalog() -> FieldCatalog:
    global _catalog
    if _catalog is None:
        from app.core.config import settings
        _catalog = FieldCatalog.from_csv_path(settings.FIELD_CATALOG_PATH)
    return _catalog


def set_catalog(catalog: FieldCatalog) -> None:
    global _catalog
    _catalog = catalog
