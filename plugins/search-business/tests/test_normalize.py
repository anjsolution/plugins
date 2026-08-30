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
    for k in ("발주유형", "상태정확", "상태첫글자", "계약방법", "지역", "제외필드", "딥링크메뉴"):
        assert k in data
    assert data["계약방법"] == {"CTA": "일반경쟁", "CTE": "지명경쟁", "CTH": "제한경쟁", "CTL": "전자수의"}
    assert not hasattr(nz, "fetch_cpt_terms_labels")
    for k in ():
        assert k in data


def test_no_inline_korean_dicts_in_python():
    src = (SCRIPTS / "_ebid/normalize.py").read_text(encoding="utf-8")
    assert '"01": "본사"' not in src
    assert '"EY": "공고중"' not in src


def test_normalize_notice_keys_and_passthrough():
    row = nz.normalize_notice(ITEM)  # 라벨 인자 생략 = codes.json 정적 매핑
    assert row["발주유형"] == "용역"
    assert row["지역"] == "수도권본부" and row["지역코드"] == "0B"
    assert row["상태"] == "입찰완료" and row["공고일"] == "2025-07-02"
    assert row["계약방법"] == "일반경쟁"
    assert row["딥링크"].startswith("https://ebid.ex.co.kr/default.do?menuId=NPRO12001&noti_id=NID")
    assert row["딥링크"].endswith("&noti_cont_id=CID&noti_no=202506507&bid_no=1&bid_rev=1")
    assert "g2b" not in row["딥링크"] and "part=" not in row["딥링크"]
    assert "..." not in row["딥링크"]
    assert nz.build_notice_deeplink({**ITEM, "noti_cont_id": None}) == ""   # 5개 필수 중 하나라도 없으면 링크 없음
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


def test_render_notice_markdown():
    n = nz.normalize_notice({**ITEM, "noti_nm": "[긴급]교통관리시스템 용역"}, {"CTA": "일반경쟁"})
    md = nz.render_notice_markdown([n], keyword="ITS", period_label="1년")
    assert "### [용역] 'ITS' 검색 결과 (1년, 1건)" in md
    assert "| 공고번호 | 지역 | 공고명 | 설계금액 | 계약방법 | 공고일 | 상태 |" in md
    assert "[\[긴급\]교통관리시스템 용역](https://ebid.ex.co.kr/default.do?menuId=NPRO12001" in md
    assert "[공사]" not in md  # 빈 유형은 표를 만들지 않는다
    assert "[계약]" not in md


def test_render_contract_markdown():
    c = nz.normalize_contract(CONTRACT)
    md = nz.render_contract_markdown([c], keyword="ITS", period_label="1년")
    assert "### [계약] 'ITS' 검색 결과 (1년, 1건)" in md
    assert "| 구분 | 공고번호 | 계약명 | 계약방법 | 사업자번호 | 계약업체 | 총계약금액 | 체결일 |" in md
    assert "| 용역 | 202603454 | 세종포천선(세종-천안) ITS구축 책임감리용역 | 일반경쟁 | 114-81-64393 | 대영유비텍 주식회사 | 706,520,000 | 2026-05-27 |" in md


def test_render_markdown_empty():
    assert "검색 결과 없음" in nz.render_notice_markdown([], keyword="x", period_label="1년")
    assert "검색 결과 없음" in nz.render_contract_markdown([], keyword="x", period_label="1년")


DETAIL = {
    "result_status": "S",
    "cntrOpnDetail": {"cntr_nm": "전주수목원 제2장미원 조성공사", "cntr_sd": "20260901", "cntr_ed": "20261229",
                      "cntr_day": 120, "poor": "전북본부", "jhhm": None, "claus_cd": None,
                      "claus_cd_etc_cause": None, "cntr_amt": 179615900, "cntg_date": "20260828"},
    "repVdInfo": [{"vd_nm": "주식회사 대한콘설탄트", "rep_nm": "이영민", "dtl_addr": "서울특별시 종로구 필운대로 9",
                   "phone_no": "027355249", "shar_rate": "60 %", "vd_sn": "false"},
                  {"vd_nm": "주식회사 드림이앤디", "rep_nm": "홍성윤", "dtl_addr": "충청남도 공주시 번영1로 156",
                   "phone_no": "0428280700", "shar_rate": "40 %", "vd_sn": "true"}],
    "deptAddr": {"chr_nm": "한정희", "chr_dept_phone_no1": "063", "chr_dept_phone_no2": "840",
                 "chr_dept_phone_no3": "0208", "chr_dept_addr": "전라북도 전주시 덕진구 번영로 420",
                 "chr_dept_post_no1": "560", "chr_dept_post_no2": "801", "opn_yn": "Y", "creator_id": "x"},
    "bidInfo": {"dsgng_amt": 199747000, "open_dt": "202608101100", "cpt_terms_str": "제한경쟁",
                "lmtcpt_apply_bas_cd_str": "지역", "stl_terms_str": "적격심사", "pq_type_str": "없음",
                "unsc_dty_yn_str": "없음", "bid_nm": "전주수목원 제2장미원 조성공사", "plrl_prc_yn": "Y"},
    "cntrBasInfo": {"expt_amt": 199155250, "noti_nm": "[긴급]전주수목원 제2장미원 조성공사",
                    "noti_date": "20260804", "chr_nm": "한정희"},
    "getSwYn": None,
}


def test_normalize_contract_detail_competitive():
    d = nz.normalize_contract_detail(DETAIL)
    assert d["계약기간"] == "2026-09-01~2026-12-29" and d["계약일수"] == 120
    assert d["발주처"] == "전북본부"
    assert d["담당자"] == "한정희" and d["담당부서전화"] == "063-840-0208"
    assert d["담당부서주소"] == "전라북도 전주시 덕진구 번영로 420"
    assert d["수의근거"] == ""
    assert [v["업체명"] for v in d["계약업체상세"]] == ["주식회사 대한콘설탄트", "주식회사 드림이앤디"]
    assert d["계약업체상세"][0]["대표자"] == "이영민" and d["계약업체상세"][0]["지분율"] == "60 %"
    assert d["설계금액원"] == 199747000 and d["예정가격원"] == 199155250
    assert d["개찰일시"] == "2026-08-10 11:00" and d["제한기준"] == "지역" and d["낙찰방법"] == "적격심사"
    assert d["공고명"] == "[긴급]전주수목원 제2장미원 조성공사" and d["공고일"] == "2026-08-04"
    assert d["SW계약여부"] == ""


def test_normalize_contract_detail_private_contract_without_bid_info():
    priv = {**DETAIL, "bidInfo": None, "cntrBasInfo": None,
            "cntrOpnDetail": {**DETAIL["cntrOpnDetail"], "jhhm": "026조 01항 05호 가목",
                              "claus_cd_etc_cause": "추정가격 5천만원 이하의 계약"}}
    d = nz.normalize_contract_detail(priv)
    assert d["수의근거"] == "026조 01항 05호 가목 — 추정가격 5천만원 이하의 계약"
    assert d["설계금액원"] is None and d["예정가격원"] is None and d["공고명"] == ""


def test_render_contract_markdown_with_detail():
    c = nz.normalize_contract(CONTRACT)
    c["상세"] = nz.normalize_contract_detail(DETAIL)
    md = nz.render_contract_markdown([c], keyword="ITS", period_label="1년", detail=True)
    assert "| 구분 | 공고번호 | 계약명 | 계약방법 | 계약업체 | 대표자 | 총계약금액 | 예정가격 | 체결일 | 계약기간 | 발주처 | 담당자 | 수의근거 |" in md
    assert "| 이영민(60 %), 홍성윤(40 %) |" in md
    assert "| 한정희 (063-840-0208) |" in md
    assert "| 2026-09-01~2026-12-29 |" in md


def test_biz_no_format():
    assert nz._biz_no("1148164393") == "114-81-64393"
    assert nz._biz_no("") == "-"
    assert nz._biz_no("12345") == "12345"


def test_render_titles_without_keyword():
    n = nz.normalize_notice(ITEM, {"CTA": "일반경쟁"})
    c = nz.normalize_contract(CONTRACT)
    assert "### [용역] 전체 공고 (2026-08-01~2026-08-30, 1건)" in nz.render_notice_markdown(
        [n], keyword="", period_label="2026-08-01~2026-08-30")
    assert "### [계약] 전체 계약 (2026-08-01~2026-08-30, 1건)" in nz.render_contract_markdown(
        [c], keyword="", period_label="2026-08-01~2026-08-30")
    assert "검색 결과 없음" in nz.render_notice_markdown([], keyword="", period_label="1년")


def test_search_contracts_omits_cntr_nm_when_no_keyword(monkeypatch):
    from _ebid import contracts
    sent = {}
    monkeypatch.setattr(contracts, "_post_json", lambda client, path, body: sent.update(body) or [])
    contracts.search_contracts(None, keyword=None, from_date="20260801", to_date="20260830")
    assert "cntr_nm" not in sent
    sent.clear()
    contracts.search_contracts(None, keyword="터널", from_date="20260801", to_date="20260830", notice_class="SV")
    assert sent["cntr_nm"] == "터널" and sent["gubun"] == "SV"
