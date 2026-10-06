from app.services.field_catalog import FieldCatalog

CSV = """No,Doc Group,Field Code,Field Name (EN),ชื่อฟิลด์ (TH),Other keyword,Source Document,Granularity / Repeat,Type,Example,Allowed Values / Validation
1,Claim History,CLM_END+C4:F13,Claim End Date,วันสิ้นงวดเคลม,,Claim report,per policy year,Date,31/12/2026,DD/MM/YYYY(AD)
2,Claim History,CLM_AMT_IPD,Claim amount - IPD,ยอดเคลม IPD,,Claim report,per policy year,Number,1000,THB ≥ 0
3,Claim History,CLM_CNT_<BEN>,Claim count - per benefit,จำนวนครั้งเคลม,,Claim report,per policy year,Number,35,> 0
4,Existing Benefit,BEN_SMM_COINS,SMM Co-insurance,สัดส่วนร่วมจ่าย SMM,Co-insurance; ร่วมจ่าย,Benefit,per plan,Text,80/20,100/0 | 90/10 | 80/20 | 70/30
5,Existing Benefit,FCL_MAX,Maximum FCL,ทุนสูงสุด,FCL; Free Cover Limit,Benefit schedule /,1 per case,Number,3500000,THB ≥ 0
6,Census,CEN_RELATION,Relation,ความสัมพันธ์,Employee; Spouse,Census file,per member,Enum,E,E = Employee | S = Spouse | C = Child
"""


def test_catalog_parses_and_expands():
    cat = FieldCatalog.from_csv_text(CSV)
    codes = {s.field_code for s in cat.specs}
    assert "CLM_END" in codes and "CLM_END+C4:F13" not in codes
    assert "CLM_CNT_IPD" in codes and "CLM_CNT_<BEN>" not in codes
    assert cat.get("FCL_MAX").scope == "case" and cat.get("BEN_SMM_COINS").scope == "group"
    assert cat.get("BEN_SMM_COINS").allowed_values == ["100/0", "90/10", "80/20", "70/30"]
    assert cat.get("CEN_RELATION").enum_aliases["spouse"] == "S"
    assert cat.codes("CENSUS") == ["CEN_RELATION"]


def test_prompt_block_contains_keywords():
    cat = FieldCatalog.from_csv_text(CSV)
    block = cat.prompt_block("BENEFIT_SCHEDULE")
    assert "FCL_MAX" in block and "Free Cover Limit" in block and "| Text |" in block
    assert "| scope |" in block and "| case |" in block and "| group |" in block
