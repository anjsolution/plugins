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
