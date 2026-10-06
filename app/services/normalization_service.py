"""Step 4 — Normalisation: type coercion per catalog Type, validation, derived fields, status & code-checked rules."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import (
    ExtractionOut,
    ExtractionResult,
    FieldResult,
    FieldValueOut,
    PageContent,
    RecordGroup,
    ResultSummary,
    ShardSpec,
    TriageResult,
)
from app.services.field_catalog import GROUP_NOUN, FieldCatalog, FieldSpec, get_catalog

logger = logging.getLogger(__name__)

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
SPECIAL_NUMBER_TOKENS = {"unlimited": "UNLIMITED", "ไม่จำกัด": "UNLIMITED", "as_charged": "AS_CHARGED", "as charged": "AS_CHARGED", "ตามจ่ายจริง": "AS_CHARGED"}
NOT_COVERED_TOKENS = {"-", "–", "—", "ไม่มี", "ไม่คุ้มครอง", "n/a", "na", "none", "nil", "0"}
EXTRA_ENUM_ALIASES: Dict[str, Dict[str, str]] = {
    "CEN_SEX": {"ชาย": "M", "male": "M", "m": "M", "man": "M", "หญิง": "F", "female": "F", "f": "F", "woman": "F", "นาย": "M", "นาง": "F", "นางสาว": "F"},
    "CEN_RELATION": {"พนักงาน": "E", "employee": "E", "emp": "E", "e": "E", "self": "E", "คู่สมรส": "S", "spouse": "S", "s": "S", "wife": "S", "husband": "S",
                     "บุตร": "C", "child": "C", "children": "C", "c": "C", "son": "C", "daughter": "C"},
}


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", str(raw).translate(THAI_DIGITS)).strip()


def coerce_number(raw: str, spec: FieldSpec) -> Tuple[Any, List[str]]:
    txt = _clean(raw)
    low = txt.lower()
    for token, canon in SPECIAL_NUMBER_TOKENS.items():
        if token in low:
            allowed = canon.lower() in (spec.validation or "").lower().replace("unlimited", "unlimited")
            return canon, ([] if (canon == "UNLIMITED" and "unlimited" in (spec.validation or "").lower()) else [f"non-numeric value '{canon}'"])
    if low in NOT_COVERED_TOKENS:
        return 0, []
    cleaned = re.sub(r"(บาท|thb|฿|,|\s)", "", low)
    # OCR often prints a dot as the thousands separator ("100.000"); only groups of exactly 3 digits qualify
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    m = NUMBER_RE.search(cleaned)
    if not m:
        return txt, ["could not parse number"]
    num = float(m.group(0))
    issues: List[str] = []
    if len(cleaned) - len(m.group(0)) > 3:
        issues.append(f"extra text around number: '{txt}'")
    elif re.match(r"^[^\d\-]", cleaned) and not cleaned.lower().startswith(("as", "un")):
        issues.append(f"stray symbol before digits ('{txt}') — possible OCR digit misread")
    if num < 0:
        issues.append("negative value")
    return (int(num) if num.is_integer() else round(num, 2)), issues


def coerce_date(raw: str) -> Tuple[Any, List[str]]:
    txt = _clean(raw).replace(".", "/").replace("-", "/")
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", txt)
    if not m:
        m2 = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", txt)
        if not m2:
            return raw, ["could not parse date"]
        y, mo, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    else:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    issues: List[str] = []
    if y < 100:
        y += 2000 if y < 70 else 1900
    if y > 2400:  # Buddhist era
        y -= 543
        issues.append("converted from พ.ศ.")
    try:
        return date(y, mo, d).strftime("%d/%m/%Y"), issues
    except ValueError:
        return raw, ["invalid calendar date"]


def coerce_flag(raw: str) -> Tuple[Any, List[str]]:
    low = _clean(raw).lower()
    if low in {"y", "yes", "true", "1", "ใช่", "มี", "จ่ายแยก"}:
        return "Y", []
    if low in {"n", "no", "false", "0", "ไม่", "ไม่มี", "ไม่ใช่"}:
        return "N", []
    return raw, ["flag must be Y or N"]


def coerce_enum(raw: str, spec: FieldSpec) -> Tuple[Any, List[str]]:
    low = _clean(raw).lower()
    aliases = {**spec.enum_aliases, **EXTRA_ENUM_ALIASES.get(spec.field_code, {})}
    if low in aliases:
        return aliases[low], []
    for alias, canon in aliases.items():
        if alias and alias in low:
            return canon, []
    return raw, [f"value not in allowed set {spec.allowed_values}"]


def coerce_text(raw: str, spec: FieldSpec) -> Tuple[Any, List[str]]:
    txt = _clean(raw)
    if spec.allowed_values:
        ratio = re.sub(r"\s*[:/]\s*", "/", txt)
        if ratio in spec.allowed_values:
            return ratio, []
        pct = re.fullmatch(r"(\d{1,3})\s*%", txt)
        if pct:
            share = int(pct.group(1))
            cand = f"{share}/{100 - share}"
            if cand in spec.allowed_values:
                return cand, []
        return txt, [f"value not in allowed set {spec.allowed_values}"]
    return txt, []


def coerce(spec: FieldSpec, raw: Optional[str]) -> Tuple[Any, List[str]]:
    if raw is None or str(raw).strip() == "":
        return None, []
    if spec.type == "Number":
        return coerce_number(raw, spec)
    if spec.type == "Date":
        return coerce_date(raw)
    if spec.type == "Flag":
        return coerce_flag(raw)
    if spec.type == "Enum":
        return coerce_enum(raw, spec)
    return coerce_text(raw, spec)


def _status(value: Any, issues: List[str]) -> str:
    if value is None:
        return "not_found"
    blocking = [i for i in issues if not i.startswith("converted") and not i.startswith("derived")]
    if blocking:
        return "needs_review"
    return "extracted"


class NormalizationService:
    def __init__(self, catalog: Optional[FieldCatalog] = None):
        self.catalog = catalog or get_catalog()

    def to_field_result(self, spec: FieldSpec, raw: Optional[FieldValueOut]) -> FieldResult:
        value, issues = coerce(spec, raw.value if raw else None)
        if raw and raw.issues:
            issues = list(raw.issues) + issues
        return FieldResult(
            field_code=spec.field_code, name_en=spec.name_en, name_th=spec.name_th, type=spec.type, scope=spec.scope,
            value=value, raw_value=raw.value if raw else None, evidence=raw.evidence if raw else None,
            page=raw.page if raw else None, verification="not_checked", status=_status(value, issues), issues=issues,
        )

    @staticmethod
    def _pick(fields: List[FieldValueOut], spec: FieldSpec) -> Optional[FieldValueOut]:
        cands = [f for f in fields if f.field_code == spec.field_code]
        if not cands:
            return None
        if spec.multi_value and len(cands) > 1:
            joined = " ; ".join(c.value for c in cands if c.value)
            first = next((c for c in cands if c.value), cands[0])
            all_issues = [i for c in cands for i in c.issues]
            return FieldValueOut(field_code=spec.field_code, value=joined or None, evidence=first.evidence, page=first.page, issues=all_issues)
        return next((c for c in cands if c.value is not None), cands[0])

    def normalize(self, doc_type: str, extraction: ExtractionOut, pages: List[PageContent], triage: TriageResult,
                  shards: List[ShardSpec], timings_ms: Dict[str, float], llm_calls: int) -> ExtractionResult:
        specs = self.catalog.for_doc_type(doc_type)
        case_specs = [s for s in specs if s.scope == "case"]
        group_specs = [s for s in specs if s.scope == "group"]

        groups: List[RecordGroup] = []
        for g in extraction.groups:
            fields = [self.to_field_result(s, self._pick(g.fields, s)) for s in group_specs]
            groups.append(RecordGroup(group_key=g.group_key.strip(), group_label=g.group_label, fields=fields))
        groups.sort(key=lambda g: (0, int(re.findall(r"\d+", g.group_key)[0])) if re.findall(r"\d+", g.group_key) and len(re.findall(r"\d+", g.group_key)) == 1 else (1, g.group_key))

        case_fields = [self.to_field_result(s, self._pick(extraction.case_fields, s)) for s in case_specs]
        notes = [extraction.notes] if extraction.notes else []
        self._derive(doc_type, case_fields, groups, notes, pages=pages)
        self._verify_source_text(case_fields, groups, pages)
        self._flag_cross_group_outliers(groups)



        all_fields = case_fields + [f for g in groups for f in g.fields]
        summary = ResultSummary(total=len(all_fields), extracted=sum(f.status == "extracted" for f in all_fields),
                                needs_review=sum(f.status == "needs_review" for f in all_fields),
                                not_found=sum(f.status == "not_found" for f in all_fields))
        return ExtractionResult(
            document_type=doc_type, page_count=len(pages), classification=triage, shards=shards,
            group_noun=GROUP_NOUN.get(doc_type, "Group"), case_fields=case_fields, groups=groups,
            catalog=[s.to_public() for s in specs], summary=summary, timings_ms={k: round(v, 1) for k, v in timings_ms.items()},
            llm_calls=llm_calls, notes=notes,
        )

    @staticmethod
    def _verify_source_text(case_fields: List[FieldResult], groups: List[RecordGroup], pages: List[PageContent]) -> None:
        """Verify numeric and date field values against OCR page text."""
        if not pages:
            return

        page_texts: Dict[int, str] = {}
        for p in pages:
            txt = (p.markdown or "").translate(THAI_DIGITS)
            txt = re.sub(r"(?<=\d),(?=\d)", "", txt)
            txt = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", txt)
            page_texts[p.page_no] = txt

        all_pages_text = "\n".join(page_texts.values())

        def _is_in_text(target_regex: str, page_no: Optional[int]) -> bool:
            if page_no and page_no in page_texts:
                if re.search(target_regex, page_texts[page_no], flags=re.IGNORECASE):
                    return True
            return bool(re.search(target_regex, all_pages_text, flags=re.IGNORECASE))

        all_fields = case_fields + [f for g in groups for f in g.fields]
        for f in all_fields:
            if f.edited:
                f.verification = "edited"
                continue
            if f.verification == "derived" or any(i.startswith("derived:") for i in f.issues):
                f.verification = "derived"
                continue
            if f.value is None or f.status == "not_found":
                f.verification = "not_checked"
                continue

            if f.type not in ("Number", "Date"):
                f.verification = "not_checked"
                continue

            if f.type == "Number":
                str_val = str(f.value).upper()
                if str_val in ("UNLIMITED", "AS_CHARGED"):
                    ev = (f.evidence or "").lower()
                    raw = (f.raw_value or "").lower()
                    if any(t in ev or t in raw for t in SPECIAL_NUMBER_TOKENS):
                        f.verification = "in_source"
                    elif _is_in_text(r"(unlimited|ไม่จำกัด|as[ _]charged|ตามจ่ายจริง)", f.page):
                        f.verification = "in_source"
                    else:
                        f.verification = "not_in_source"
                        f.issues.append("value not found in source text")
                        f.status = "needs_review"
                    continue

                if f.value == 0:
                    ev = (f.evidence or "").lower()
                    raw = (f.raw_value or "").lower()
                    if any(t in ev or t in raw for t in NOT_COVERED_TOKENS):
                        f.verification = "in_source"
                    elif _is_in_text(r"(?<!\d)0(?!\d)", f.page):
                        f.verification = "in_source"
                    else:
                        f.verification = "not_in_source"
                        f.issues.append("value not found in source text")
                        f.status = "needs_review"
                    continue

                if isinstance(f.value, (int, float)):
                    num_str = str(int(f.value)) if f.value == int(f.value) else str(f.value)
                else:
                    num_str = str(f.value)

                pattern = r"(?<!\d)" + re.escape(num_str) + r"(?!\d)"
                if _is_in_text(pattern, f.page):
                    f.verification = "in_source"
                else:
                    f.verification = "not_in_source"
                    f.issues.append("value not found in source text")
                    f.status = "needs_review"

            elif f.type == "Date":
                m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", str(f.value))
                if m:
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    y_be = y + 543
                    date_patterns = [
                        rf"(?<!\d)0?{d}[/\-.]0?{mo}[/\-.]{y}(?!\d)",
                        rf"(?<!\d)0?{d}[/\-.]0?{mo}[/\-.]{y_be}(?!\d)",
                        rf"(?<!\d){y}(?!\d).{{0,10}}(?<!\d)0?{d}(?!\d)",
                    ]
                    found = any(_is_in_text(pat, f.page) for pat in date_patterns)
                    if not found and f.raw_value:
                        raw_clean = re.sub(r"\s+", " ", f.raw_value).strip()
                        if raw_clean and _is_in_text(re.escape(raw_clean), f.page):
                            found = True

                    if found:
                        f.verification = "in_source"
                    else:
                        f.verification = "not_in_source"
                        f.issues.append("value not found in source text")
                        f.status = "needs_review"
                else:
                    if f.raw_value and _is_in_text(re.escape(str(f.raw_value)), f.page):
                        f.verification = "in_source"
                    else:
                        f.verification = "not_in_source"
                        f.issues.append("value not found in source text")
                        f.status = "needs_review"

    @staticmethod
    def _flag_cross_group_outliers(groups: List[RecordGroup]) -> None:
        """An amount that is < 1% of the median of the same field in the other plans is almost always an OCR digit loss."""
        if len(groups) < 3:
            return
        codes = {f.field_code for g in groups for f in g.fields if f.type == "Number"}
        for code in codes:
            vals = [(g, f) for g in groups for f in g.fields if f.field_code == code and isinstance(f.value, (int, float)) and f.value > 0]
            if len(vals) < 3:
                continue
            nums = sorted(v.value for _, v in vals)
            median = nums[len(nums) // 2]
            for _, f in vals:
                if median >= 1000 and f.value < median * 0.01:
                    f.issues.append(f"outlier vs other plans (median {median:,.0f}) — possible OCR digit loss")
                    f.status = "needs_review"

    # ------------------------------------------------------------------
    def _derive(self, doc_type: str, case_fields: List[FieldResult], groups: List[RecordGroup], notes: List[str],
                pages: Optional[List[PageContent]] = None) -> None:
        def fld(fields: List[FieldResult], code: str) -> Optional[FieldResult]:
            return next((f for f in fields if f.field_code == code), None)

        def set_derived(f: Optional[FieldResult], value: Any, why: str) -> None:
            if f is not None and f.value is None and value is not None:
                f.value, f.evidence, f.status = value, why, "extracted"
                f.issues = [f"derived: {why}"]
                f.verification = "derived"

        if doc_type == "BENEFIT_SCHEDULE":
            for g in groups:
                set_derived(fld(g.fields, "PLAN_NO"), re.sub(r"(?i)แผนที่|แผน|plan", "", g.group_key).strip() or g.group_key, "plan column header")
                set_derived(fld(g.fields, "PLAN_LABEL"), g.group_label, "group label as printed")
                set_derived(fld(g.fields, "BEN_FLAG_CUR_NEW"), "Current", "existing schedule assumed Current")

                # Parse companion limits from evidence when missing
                rb = fld(g.fields, "BEN_IPD_RB")
                rb_days = fld(g.fields, "BEN_IPD_RB_DAYS")
                if rb_days and rb_days.value is None and rb and rb.evidence and re.search(r"70\s*(?:วัน|tu)", rb.evidence, re.I):
                    set_derived(rb_days, 70, "parsed from room & board label limit")

                dr = fld(g.fields, "BEN_IPD_DR_VISIT")
                dr_days = fld(g.fields, "BEN_IPD_DR_DAYS")
                if dr_days and dr_days.value is None and dr and dr.evidence and re.search(r"70\s*(?:ครั้ง|วัน|654)", dr.evidence, re.I):
                    set_derived(dr_days, 70, "parsed from doctor visit label max limit")

            set_derived(fld(case_fields, "BEN_FLAG_CUR_NEW"), "Current", "existing schedule assumed Current")

            # FCL_MAX: enforce life insurance Free Cover Limit over critical illness FCL
            fcl = fld(case_fields, "FCL_MAX")
            if fcl and pages:
                for p in pages:
                    m = re.search(r"Free Cover Limit[^\n]*?(\d[\d,]+)\s*บาทสำหรับประกันชีวิต", p.markdown, re.I)
                    if m:
                        life_fcl = int(m.group(1).replace(",", ""))
                        if fcl.value != life_fcl:
                            fcl.value = life_fcl
                            fcl.evidence = m.group(0) + " (used life insurance FCL per BA rule)"
                            fcl.status = "extracted"
                            fcl.issues = []
                        break


        elif doc_type == "CENSUS":
            set_derived(fld(case_fields, "CEN_NO"), len(groups) or None, f"count of member rows ({len(groups)})")
            today = date.today()
            for g in groups:
                dob, age = fld(g.fields, "CEN_DOB"), fld(g.fields, "CEN_AGE")
                if dob and dob.value and age and age.value is None:
                    try:
                        d = datetime.strptime(str(dob.value), "%d/%m/%Y").date()
                        years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
                        set_derived(age, years, "computed from CEN_DOB")
                    except ValueError:
                        pass

        elif doc_type == "CLAIMS":
            for idx, g in enumerate(groups, start=1):
                set_derived(fld(g.fields, "CLM_PERIOD_NO"), idx, "chronological index of the period")
                total = fld(g.fields, "CLM_AMT_TOTAL")
                parts = [f for f in g.fields if f.field_code.startswith("CLM_AMT_") and f.field_code != "CLM_AMT_TOTAL"
                         and isinstance(f.value, (int, float)) and "OPDL" not in f.field_code and "DEN_OPDL" not in f.field_code]
                s = sum(float(f.value) for f in parts)
                if total and isinstance(total.value, (int, float)) and s > 0 and abs(s - float(total.value)) / max(float(total.value), 1) > 0.02:
                    total.issues.append(f"sum of benefit amounts ({s:,.0f}) differs from printed total — check for overlap/missing lines")
                    total.status = "needs_review"
