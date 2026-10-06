from app.models.schemas import ExtractionOut, FieldValueOut, PageContent, PageTriage, RecordGroupOut, TriageResult
from app.services.field_catalog import get_catalog
from app.services.normalization_service import NormalizationService, coerce

cat = get_catalog()


def test_coerce_number_variants():
    assert coerce(cat.get("BEN_IPD_RB"), "2,500 บาท") == (2500, [])
    assert coerce(cat.get("BEN_GTL"), "-") == (0, [])
    assert coerce(cat.get("BEN_IPD_RB_DAYS"), "ไม่จำกัด")[0] == "UNLIMITED"
    value, issues = coerce(cat.get("BEN_IPD_RB"), "10 เท่าของค่าห้อง")
    assert issues  # flagged for review


def test_coerce_date_buddhist_era():
    value, issues = coerce(cat.get("CEN_DOB"), "08/10/2528")
    assert value == "08/10/1985" and issues == ["converted from พ.ศ."]


def test_coerce_enum_and_text_ratio():
    assert coerce(cat.get("CEN_SEX"), "หญิง") == ("F", [])
    assert coerce(cat.get("CEN_RELATION"), "Spouse") == ("S", [])
    assert coerce(cat.get("BEN_SMM_COINS"), "80 : 20") == ("80/20", [])
    assert coerce(cat.get("BEN_SMM_COINS"), "80%") == ("80/20", [])
    assert coerce(cat.get("BEN_IPD_ER_EXCL_OHS"), "yes") == ("Y", [])


def _triage(n=1):
    return TriageResult(document_type="BENEFIT_SCHEDULE", reasoning="t",
                        pages=[PageTriage(page=i, role="BENEFIT_TABLE", is_relevant=True) for i in range(1, n + 1)])


def test_normalize_fills_every_catalog_field_and_derives_plan_no():
    out = ExtractionOut(
        case_fields=[FieldValueOut(field_code="FCL_MAX", value="2,000,000", evidence="Free Cover Limit", page=1)],
        groups=[RecordGroupOut(group_key="แผนที่ 1", group_label="Sr. M", fields=[
            FieldValueOut(field_code="BEN_IPD_RB", value="2500", evidence="ค่าห้อง", page=1),
            FieldValueOut(field_code="BEN_GTL", value="300,000", evidence="ชีวิต", page=1),
        ])],
        notes=None,
    )
    # Page 1 markdown contains 2,000,000 and 2,500, but not 300,000
    page = PageContent(page_no=1, source_file="x", markdown="Free Cover Limit 2,000,000 บาท ค่าห้อง 2,500")
    result = NormalizationService(cat).normalize("BENEFIT_SCHEDULE", out, [page], _triage(), [], {}, 1)
    g = result.groups[0]
    codes = [f.field_code for f in g.fields]
    assert len(codes) == len(set(codes)) == len([s for s in cat.for_doc_type("BENEFIT_SCHEDULE") if s.scope == "group"])
    by = {f.field_code: f for f in g.fields}
    assert by["BEN_IPD_RB"].value == 2500 and by["BEN_IPD_RB"].status == "extracted" and by["BEN_IPD_RB"].verification == "in_source"
    assert by["BEN_GTL"].status == "needs_review" and by["BEN_GTL"].verification == "not_in_source"
    assert "value not found in source text" in by["BEN_GTL"].issues
    assert by["PLAN_NO"].value == "1" and by["PLAN_NO"].issues[0].startswith("derived") and by["PLAN_NO"].verification == "derived"
    assert by["BEN_DEN"].status == "not_found"
    fcl = next(f for f in result.case_fields if f.field_code == "FCL_MAX")
    assert fcl.value == 2000000 and fcl.verification == "in_source"
    assert result.summary.total == len(result.case_fields) + len(g.fields)


def test_coerce_number_dot_thousands_separator():
    assert coerce(cat.get("BEN_GTL"), "100.000") == (100000, [])
    assert coerce(cat.get("CEN_SA_FIXED"), "150,000.00") == (150000, [])
    assert coerce(cat.get("BEN_IPD_RB"), "1.5")[0] == 1.5


def test_ocr_plausibility_flags():
    v, issues = coerce(cat.get("BEN_IPD_OHS"), "$4,000")
    assert v == 4000 and any("stray symbol" in i for i in issues)
    from app.models.schemas import FieldResult, RecordGroup
    groups = [RecordGroup(group_key=str(i), fields=[FieldResult(field_code="BEN_GADD", type="Number", value=v, status="extracted")])
              for i, v in enumerate([3000000, 3000000, 3, 5000000], start=1)]
    NormalizationService._flag_cross_group_outliers(groups)
    assert groups[2].fields[0].status == "needs_review" and groups[0].fields[0].status == "extracted"


def test_source_text_verification_found_and_not_found():
    """Step 6: value not found in source text is flagged with issue and needs_review."""
    out = ExtractionOut(
        case_fields=[],
        groups=[RecordGroupOut(group_key="1", fields=[
            FieldValueOut(field_code="BEN_IPD_RB", value="4000", evidence="ค่าห้อง", page=1),
            FieldValueOut(field_code="BEN_GTL", value="54000", evidence="ชีวิต", page=1),
        ])],
    )
    # The source markdown has 54,000, but not 4,000
    page = PageContent(page_no=1, source_file="x", markdown="ชีวิต 54,000 บาท")
    result = NormalizationService(cat).normalize("BENEFIT_SCHEDULE", out, [page], _triage(), [], {}, 1)
    by = {f.field_code: f for f in result.groups[0].fields}
    assert by["BEN_GTL"].verification == "in_source" and by["BEN_GTL"].status == "extracted"
    assert by["BEN_IPD_RB"].verification == "not_in_source" and by["BEN_IPD_RB"].status == "needs_review"
    assert "value not found in source text" in by["BEN_IPD_RB"].issues


def test_source_text_verification_date_buddhist_era():
    """Step 6: Date normalized to AD matches BE year (year + 543) printed in source text."""
    tri = TriageResult(document_type="CENSUS", reasoning="t", pages=[PageTriage(page=1, role="CENSUS_TABLE", is_relevant=True)])
    out = ExtractionOut(
        case_fields=[],
        groups=[RecordGroupOut(group_key="001", fields=[
            # Model extracted 15/05/2024 (AD)
            FieldValueOut(field_code="CEN_DOB", value="15/05/2024", page=1),
        ])],
    )
    # OCR printed BE year 2567 (= 2024 + 543)
    page = PageContent(page_no=1, source_file="x", markdown="รหัส 001 วันเกิด 15/05/2567")
    result = NormalizationService(cat).normalize("CENSUS", out, [page], tri, [], {}, 1)
    by = {f.field_code: f for f in result.groups[0].fields}
    assert by["CEN_DOB"].value == "15/05/2024"
    assert by["CEN_DOB"].verification == "in_source"
    assert by["CEN_DOB"].status == "extracted"
