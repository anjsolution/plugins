import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

from _ebid import normalize as nz  # noqa: E402

ITEM = {
    "noti_no": "202506507", "noti_nm": "교통관리시스템 용역", "noti_cls": "SV",
    "area": "0B", "noti_date": "20250702", "prog_sts": "UB", "cpt_terms": "CTA",
    "dsgng_amt": 1000, "bid_end_dt": "202507101400", "open_dt": "202507101500",
    "bid_rev": 1, "noti_id": "NID", "noti_cont_id": "CID", "bid_no": 1,
    "sys_id": "NEBID", "page": "noti", "fngprt_bid_yn": "Y",
    "pq_yn": "N", "bid_shpr1": "건설기술용역", "noti_view_cnt": 12,
}


def test_codes_json_loads_and_has_sections():
    data = json.loads((SCRIPTS / "_ebid/codes.json").read_text(encoding="utf-8"))
    for k in ("발주유형", "상태정확", "상태첫글자", "계약방법폴백", "지역", "제외필드", "딥링크메뉴"):
        assert k in data


def test_no_inline_korean_dicts_in_python():
    src = (SCRIPTS / "_ebid/normalize.py").read_text(encoding="utf-8")
    assert '"01": "본사"' not in src
    assert '"EY": "공고중"' not in src


def test_normalize_notice_keys_and_passthrough():
    row = nz.normalize_notice(ITEM, {"CTA": "일반경쟁"})
    assert row["발주유형"] == "용역"
    assert row["지역"] == "수도권본부" and row["지역코드"] == "0B"
    assert row["상태"] == "입찰완료" and row["공고일"] == "2025-07-02"
    assert row["계약방법"] == "일반경쟁"
    assert row["딥링크"].startswith("https://ebid.ex.co.kr/default.do?menuId=NPRO12001&noti_id=NID")
    assert "..." not in row["딥링크"]
    assert row["noti_view_cnt"] == 12          # passthrough
    assert "sys_id" not in row                 # 제외필드


def test_prog_sts_fallback_by_initial():
    assert nz.prog_sts_label("EZ") == "공고중"
    assert nz.prog_sts_label("QQ") == "QQ"


def test_fmt_dt():
    assert nz.fmt_dt("202603261400") == "2026-03-26 14:00"
    assert nz.fmt_dt("20260326") == "2026-03-26"


CONTRACT = {"noti_cls": "SV", "cntr_nm": "세종포천선(세종-천안) ITS구축 책임감리용역", "cntg_date": "20260527",
            "g2b_snd_cpt_terms": "일반경쟁", "cntr_amt": 706520000, "com_nm": "대영유비텍 주식회사",
            "biz_no": "1148164393", "stl_noti_no": "20260345441", "svsn_dept_nm": "시설처", "cntr_dept_nm": "재무부"}


def test_normalize_contract_exposes_contract_number_and_linked_notice():
    row = nz.normalize_contract(CONTRACT)
    assert row["계약번호"] == "20260345441"
    assert row["연결공고번호"] == "202603454"
    assert row["발주유형"] == "용역" and row["체결일"] == "2026-05-27"


def test_render_markdown_notice_tables_and_contract_table():
    n = nz.normalize_notice({**ITEM, "noti_nm": "[긴급]교통관리시스템 용역"}, {"CTA": "일반경쟁"})
    c = nz.normalize_contract(CONTRACT)
    md = nz.render_markdown([n, c], keyword="ITS", period_label="1년")
    assert "### [용역] 'ITS' 검색 결과 (1년, 1건)" in md
    assert "| 공고번호 | 지역 | 공고명 | 설계금액 | 계약방법 | 공고일 | 상태 |" in md
    assert "[\[긴급\]교통관리시스템 용역](https://ebid.ex.co.kr/default.do?menuId=NPRO12001" in md
    assert "### [계약] 'ITS' 검색 결과 (1년, 1건)" in md
    assert "| 구분 | 공고번호 | 계약명 | 계약방법 | 사업자번호 | 계약업체 | 총계약금액 | 체결일 |" in md
    assert "| 용역 | 202603454 | 세종포천선(세종-천안) ITS구축 책임감리용역 | 일반경쟁 | 114-81-64393 | 대영유비텍 주식회사 | 706,520,000 | 2026-05-27 |" in md
    assert "[공사]" not in md  # 빈 유형은 표를 만들지 않는다


def test_render_markdown_empty():
    assert "검색 결과 없음" in nz.render_markdown([], keyword="x", period_label="1년")


def test_biz_no_format():
    assert nz._biz_no("1148164393") == "114-81-64393"
    assert nz._biz_no("") == "-"
    assert nz._biz_no("12345") == "12345"
