from app.models.schemas import ExtractionOut, FieldValueOut, PageContent, PageTriage, RecordGroupOut, TriageResult
from app.services.extraction_service import ExtractionService, compact_markdown, normalize_group_key
from app.services.triage_service import TriageService


def _pages(n, tokens=6000):
    return [PageContent(page_no=i, source_file=f"p{i}.jpg", markdown="x", token_estimate=tokens) for i in range(1, n + 1)]


def _triage():
    return TriageResult(document_type="BENEFIT_SCHEDULE", reasoning="t", pages=[
        PageTriage(page=1, role="COVER", is_relevant=False),
        PageTriage(page=2, role="BENEFIT_TABLE", is_relevant=True, plan_columns=["แผนที่ 1", "แผนที่ 2"]),
        PageTriage(page=3, role="BENEFIT_TABLE_CONTINUATION", is_relevant=True, continues_page=2),
        PageTriage(page=4, role="BENEFIT_TABLE", is_relevant=True, plan_columns=["แผนที่ 3", "แผนที่ 4"]),
        PageTriage(page=5, role="PLAN_DEFINITIONS", is_relevant=True, topics=["FCL"]),
        PageTriage(page=6, role="TERMS_BOILERPLATE", is_relevant=False),
    ])


def test_benefit_shards_follow_plan_columns_and_share_definitions():
    svc = ExtractionService(llm=object.__new__(type("L", (), {"enabled": False})))  # no LLM needed
    shards = svc.plan_shards("BENEFIT_SCHEDULE", _pages(6), _triage())
    assert len(shards) == 2
    assert shards[0].page_nos == [2, 3] and shards[0].shared_page_nos == [5] and shards[0].plan_columns == ["แผนที่ 1", "แผนที่ 2"]
    assert shards[1].page_nos == [4] and shards[1].shared_page_nos == [5]


def test_small_document_is_single_shard():
    svc = ExtractionService(llm=object.__new__(type("L", (), {"enabled": False})))
    shards = svc.plan_shards("BENEFIT_SCHEDULE", _pages(6, tokens=500), _triage())
    assert len(shards) == 1 and shards[0].page_nos == [2, 3, 4, 5]


def test_continuation_header_inherits_columns():
    svc = ExtractionService(llm=object.__new__(type("L", (), {"enabled": False})))
    pages = _pages(6)
    shards = svc.plan_shards("BENEFIT_SCHEDULE", pages, _triage())
    ctx = svc.build_context(shards[0], pages, _triage())
    assert "[PAGE 5 | PLAN_DEFINITIONS | shared case-level context" in ctx
    assert "BENEFIT_TABLE_CONTINUATION of page 2 | inherited columns: value column 1 → แผนที่ 1; value column 2 → แผนที่ 2" in ctx


def test_merge_unions_plans_and_first_value_rule():
    a = ExtractionOut(case_fields=[FieldValueOut(field_code="FCL_MAX", value="2000000")],
                      groups=[RecordGroupOut(group_key="แผนที่ 1", fields=[FieldValueOut(field_code="BEN_GTL", value="100000")])])
    b = ExtractionOut(case_fields=[FieldValueOut(field_code="FCL_MAX", value="2000000")],
                      groups=[RecordGroupOut(group_key="001", fields=[FieldValueOut(field_code="BEN_GTL", value="100000")]),
                              RecordGroupOut(group_key="2", fields=[])])
    merged = ExtractionService._merge([a, b])
    assert [g.group_key for g in merged.groups] == ["แผนที่ 1", "2"]  # 001 merged into plan 1
    assert merged.case_fields[0].value == "2000000"
    assert normalize_group_key("แผน 001") == "1"


def test_merge_records_shard_conflict_as_issue():
    a = ExtractionOut(case_fields=[FieldValueOut(field_code="FCL_MAX", value="2000000")],
                      groups=[RecordGroupOut(group_key="1", fields=[FieldValueOut(field_code="BEN_GTL", value="500000")])])
    b = ExtractionOut(case_fields=[FieldValueOut(field_code="FCL_MAX", value="3000000")],
                      groups=[RecordGroupOut(group_key="1", fields=[FieldValueOut(field_code="BEN_GTL", value="600000")])])
    merged = ExtractionService._merge([a, b])
    # Keeps first value
    assert merged.case_fields[0].value == "2000000"
    assert any("shard conflict" in i for i in merged.case_fields[0].issues)
    grp = merged.groups[0]
    assert grp.fields[0].value == "500000"
    assert any("shard conflict" in i for i in grp.fields[0].issues)


def test_compact_markdown_replaces_html_tables():
    p = PageContent(page_no=1, source_file="x", markdown="intro\n<table><tr><td>a</td><td>b</td></tr></table>\n<!-- PageBreak -->",
                    tables=[[["a", "b"], ["1", "2"]]])
    md = compact_markdown(p)
    assert "<table>" not in md and "| a | b |" in md and "PageBreak" not in md


def test_triage_repair_fills_missing_pages_and_continuation_parent():
    tri = TriageResult(document_type="BENEFIT_SCHEDULE", reasoning="t", pages=[
        PageTriage(page=1, role="BENEFIT_TABLE", is_relevant=True, plan_columns=["A", "B"]),
        PageTriage(page=2, role="BENEFIT_TABLE_CONTINUATION", is_relevant=False),
    ])
    fixed = TriageService._repair(tri, _pages(3), hint="CLAIMS")
    assert fixed.document_type == "CLAIMS"
    assert [p.page for p in fixed.pages] == [1, 2, 3]
    assert fixed.pages[1].continues_page == 1 and fixed.pages[1].is_relevant is True


def test_audit_coverage_finds_unmapped_numeric_rows():
    svc = ExtractionService(llm=object.__new__(type("L", (), {"enabled": False})))
    page = PageContent(page_no=1, source_file="x", tables=[[[
        "ความคุ้มครอง", "แผน 001", "แผน 002"],
        ["ค่าห้องและค่าอาหาร (สูงสุด 31 วัน)", "1,500", "3,000"],
        ["ค่าตรวจรักษาแบบผู้ป่วยนอก (30 ครั้ง/ปี)", "3,000", "1,500"],
        ["หมายเหตุ", "", ""],
    ]])
    tri = TriageResult(document_type="BENEFIT_SCHEDULE", reasoning="t",
                       pages=[PageTriage(page=1, role="BENEFIT_TABLE", is_relevant=True, plan_columns=["แผน 001", "แผน 002"])])
    out = ExtractionOut(case_fields=[], groups=[RecordGroupOut(group_key="001", fields=[
        FieldValueOut(field_code="BEN_IPD_RB", value="1500", evidence="ค่าห้องและค่าอาหาร (สูงสุด 31 วัน) | 1,500")])])
    unmapped = svc.audit_coverage([page], tri, out)
    assert [u["label"] for u in unmapped] == ["ค่าตรวจรักษาแบบผู้ป่วยนอก (30 ครั้ง/ปี)"]
    assert unmapped[0]["plan_columns"] == ["แผน 001", "แผน 002"] and unmapped[0]["cells"] == ["3,000", "1,500"]


def test_matrix_output_converts_to_groups_and_plan_sequence_fix():
    from app.models.schemas import GroupValue, MatrixExtractionOut, MatrixGroupOut, MatrixRowOut
    m = MatrixExtractionOut(case_fields=[], groups=[MatrixGroupOut(group_key="1", group_label="A"), MatrixGroupOut(group_key="2")],
                            rows=[MatrixRowOut(field_code="BEN_GTL", evidence="ชีวิต", page=2,
                                               values=[GroupValue(group_key="1", value="100000"), GroupValue(group_key="2", value=None)])])
    g = m.to_generic()
    assert [x.group_key for x in g.groups] == ["1", "2"]
    assert g.groups[0].fields[0].value == "100000" and g.groups[0].group_label == "A" and g.groups[1].fields == []

    tri = TriageResult(document_type="BENEFIT_SCHEDULE", reasoning="r", pages=[
        PageTriage(page=2, role="BENEFIT_TABLE", is_relevant=True, plan_columns=[f"แผนที่ {i}" for i in range(1, 8)]),
        PageTriage(page=5, role="BENEFIT_TABLE", is_relevant=True, plan_columns=["แผนที่ 3", "แผนที่ 9", "แผนที่ 10", "แผนที่ 11", "แผนที่ 12", "แผนที่ 13"]),
        PageTriage(page=8, role="UNDERWRITING_CONDITIONS", is_relevant=False, topics=["FCL"]),
    ])
    fixed = TriageService._repair(tri, _pages(8), hint=None)
    assert fixed.pages[4].plan_columns[0] == "แผนที่ 8" and "Header digit fixes" in fixed.reasoning
    assert fixed.pages[7].is_relevant is True


def test_ground_rows_copies_cells_by_plan_column():
    from app.models.schemas import GroupValue, MatrixExtractionOut, MatrixGroupOut, MatrixRowOut
    from app.services.extraction_service import ground_rows
    page = PageContent(page_no=7, source_file="x", tables=[[["ความคุ้มครอง", "แผนที่ 8", "แผนที่ 9"], ["ทันตกรรม (ต่อปี)", "5,000", "-"]]])
    tri = TriageResult(document_type="BENEFIT_SCHEDULE", reasoning="r",
                       pages=[PageTriage(page=7, role="BENEFIT_TABLE", is_relevant=True, plan_columns=["แผนที่ 8", "แผนที่ 9"])])
    out = MatrixExtractionOut(case_fields=[], groups=[MatrixGroupOut(group_key="8"), MatrixGroupOut(group_key="9")],
                              rows=[MatrixRowOut(field_code="BEN_DEN", evidence="ทันตกรรม", page=7, source_row="p7.t1.r1",
                                                 values=[GroupValue(group_key="8", value=None), GroupValue(group_key="9", value="5000")])])  # model shifted
    assert ground_rows(out, [page], tri, {"BEN_DEN"}) == 1
    assert [(v.group_key, v.value) for v in out.rows[0].values] == [("8", "5,000"), ("9", "-")]
    ctx_tables = ExtractionService(llm=object.__new__(type("L", (), {"enabled": False}))).build_context(
        __import__("app.models.schemas", fromlist=["ShardSpec"]).ShardSpec(shard_id="S1", label="l", page_nos=[7]), [page], tri)
    assert "[p7.t1.r1] ทันตกรรม (ต่อปี) | 5,000 | - |" in ctx_tables
    # a companion field whose values come from the label must NOT be grounded
    out.rows[0].field_code, out.rows[0].values = "BEN_IPD_RB_DAYS", [GroupValue(group_key="8", value="31"), GroupValue(group_key="9", value="31")]
    assert ground_rows(out, [page], tri, {"BEN_IPD_RB_DAYS"}) == 0


def test_keyword_candidates_from_catalog():
    svc = ExtractionService(llm=object.__new__(type("L", (), {"enabled": False})))
    assert "BEN_SMM" in svc.keyword_candidates("BENEFIT_SCHEDULE", "ผลประโยชน์สูงสุดต่อการเข้ารักษาในโรงพยาบาลต่อครั้ง")
    assert svc.keyword_candidates("BENEFIT_SCHEDULE", "12 สูญเสียนิ้วหัวแม่มือ") == []
