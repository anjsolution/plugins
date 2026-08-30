"""ebid 응답 정규화 — 아는 필드는 한글 키로, 나머지는 원본 그대로 통과(passthrough).

코드→라벨 매핑은 codes.json 한 곳에서 읽는다. 필드 의미·검증 근거는
references/ebid-필드사전.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .client import BASE_URL, EbidClient

CODES: dict[str, Any] = json.loads((Path(__file__).with_name("codes.json")).read_text(encoding="utf-8"))
CLASS_LABEL_BY_CODE: dict[str, str] = CODES["발주유형"]
PROG_STS_EXACT: dict[str, str] = CODES["상태정확"]
PROG_STS_BY_INITIAL: dict[str, str] = CODES["상태첫글자"]
CPT_TERMS_FALLBACK: dict[str, str] = CODES["계약방법폴백"]
AREA_LABELS: dict[str, str] = CODES["지역"]
NOTICE_CONSTANT_FIELDS: set[str] = set(CODES["제외필드"])
DEEPLINK_MENU: dict[str, tuple[str, str]] = {k: tuple(v) for k, v in CODES["딥링크메뉴"].items()}


def build_notice_deeplink(item: dict[str, Any]) -> str:
    menu = DEEPLINK_MENU.get(item.get("noti_cls") or "")
    if not menu or not item.get("noti_id"):
        return ""
    menu_id, part = menu
    url = (f"{BASE_URL}/default.do?menuId={menu_id}"
           f"&noti_id={item.get('noti_id')}&noti_cont_id={item.get('noti_cont_id')}"
           f"&noti_no={item.get('noti_no')}&bid_no={item.get('bid_no') or 1}"
           f"&bid_rev={item.get('bid_rev') or 1}&g2b=Y&part={part}")
    if item.get("noti_cls") == "MT":
        # 물품은 biz-renewal URL 빌더가 remicon 파라미터를 추가한다(rmcn_yn 전달, 미실측)
        url += f"&remicon={item.get('rmcn_yn') or 'N'}"
    return url

def fetch_cpt_terms_labels(client: EbidClient) -> dict[str, str]:
    """계약방법 코드 라벨(PE075*)을 사이트 공통코드 API 에서 조회. 실패 시 폴백."""
    try:
        header_name, token = client.ensure_csrf_token()
        r = client.session.post(
            BASE_URL + "/findCommonCodeAttrCdList.do",
            json={"grp_cd": "PE075*"},
            headers={"Accept": "application/json", "Content-Type": "application/json",
                     "X-Requested-With": "XMLHttpRequest", header_name: token,
                     "Referer": BASE_URL + "/default.do", "menucode": "NPRO11001"},
            timeout=20,
        )
        data = json.loads(r.content.decode("utf-8"))
        rows = data if isinstance(data, list) else next(
            (v for v in data.values() if isinstance(v, list)), [])
        labels = {row["data"]: row["label"] for row in rows
                  if isinstance(row, dict) and row.get("data") and row.get("label")}
        if labels:
            return {**CPT_TERMS_FALLBACK, **labels}
    except Exception:  # 라벨은 부가 정보 — 조회 실패가 검색을 막지 않는다
        pass
    return dict(CPT_TERMS_FALLBACK)

def prog_sts_label(code: str | None) -> str:
    if not code:
        return ""
    return PROG_STS_EXACT.get(code) or PROG_STS_BY_INITIAL.get(code[0], code)

def fmt_dt(value: Any) -> str:
    """'202603261400' → '2026-03-26 14:00' (그 외 형식은 그대로)."""
    s = str(value or "")
    if len(s) == 12 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s

def normalize_notice(item: dict[str, Any], cpt_labels: dict[str, str]) -> dict[str, Any]:
    """아는 필드만 한글 키로 정규화하고, 나머지 원본 필드는 그대로 통과시킨다.

    화이트리스트 방식은 area(지역) 유실 사고의 원인 — 정규화에
    소비되지 않은 필드는 버리지 않고 원본 키 그대로 덧붙인다. 그래야 API 에
    새 필드가 생겨도 자동으로 노출된다. 제외는 NOTICE_CONSTANT_FIELDS 만.
    """
    sts = item.get("prog_sts") or ""
    sts_label = prog_sts_label(sts)
    cpt = item.get("cpt_terms") or ""
    area = item.get("area") or ""
    row = {
        "구분": "입찰공고",
        "발주유형": CLASS_LABEL_BY_CODE.get(item.get("noti_cls"), item.get("noti_cls")),
        "공고번호": item.get("noti_no"),
        "공고명": item.get("noti_nm"),
        "지역": AREA_LABELS.get(area, area),
        "지역코드": area,
        "공고일": fmt_dt(item.get("noti_date")),
        "상태": sts_label,
        "상태코드": sts,
        "입찰단계": "입찰 마감(결과 조회 가능)" if sts_label in ("입찰완료",)
        else ("취소됨" if sts_label == "취소공고" else "입찰 진행 중"),
        "계약방법": cpt_labels.get(cpt, cpt),
        "계약방법코드": cpt,
        "제한유형코드": item.get("lmtcpt_apply_bas_cd") or "",
        "업종": item.get("bid_shpr1") or "",
        "PQ여부": item.get("pq_yn") or "",
        "설계금액원": item.get("dsgng_amt"),
        "입찰마감일시": fmt_dt(item.get("bid_end_dt")),
        "개찰일시": fmt_dt(item.get("open_dt")),
        "차수": item.get("bid_rev"),
        "딥링크": build_notice_deeplink(item),
    }
    consumed = {
        "noti_cls", "noti_no", "noti_nm", "area", "noti_date", "prog_sts",
        "cpt_terms", "lmtcpt_apply_bas_cd", "dsgng_amt", "bid_end_dt", "open_dt",
        "bid_rev", "pq_yn",
        # bid_shpr1_ct/_sv 는 bid_shpr1 과 전 건 동일값(프로파일링 184건) — 업종으로 소비
        "bid_shpr1", "bid_shpr1_ct", "bid_shpr1_sv",
    }
    row.update({k: v for k, v in item.items()
                if k not in consumed and k not in NOTICE_CONSTANT_FIELDS})
    return row

def normalize_contract(item: dict[str, Any]) -> dict[str, Any]:
    """normalize_notice 와 같은 원칙 — 정규화 안 된 원본 필드는 그대로 통과."""
    stl = str(item.get("stl_noti_no") or "")
    row = {
        "구분": "계약",
        "발주유형": CLASS_LABEL_BY_CODE.get(item.get("noti_cls"), item.get("noti_cls")),
        "계약명": item.get("cntr_nm"),
        "체결일": fmt_dt(item.get("cntg_date")),
        "계약방법": item.get("g2b_snd_cpt_terms"),
        "계약금액원": item.get("cntr_amt"),
        "업체명": item.get("com_nm"),
        "사업자번호": item.get("biz_no"),
        "연결공고번호": stl[:-2] if len(stl) > 2 else stl,
        # 주관부서 = 실수요 부서("시설처 전기부" 등) — 계약부서(재무부 류 행정 부서)와 구분
        "주관부서": item.get("svsn_dept_nm"),
        "계약부서": item.get("cntr_dept_nm"),
    }
    consumed = {"noti_cls", "cntr_nm", "cntg_date", "g2b_snd_cpt_terms", "cntr_amt",
                "com_nm", "biz_no", "stl_noti_no", "svsn_dept_nm", "cntr_dept_nm"}
    row.update({k: v for k, v in item.items() if k not in consumed})
    return row

def print_table(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        if r["구분"] == "입찰공고":
            amt = f"{r['설계금액원']:,}" if r.get("설계금액원") else "-"
            print(f"[{r['발주유형']}] {r['공고번호']} | {r['지역'] or '-'} | {r['공고일']}"
                  f" | {r['상태']} | {r['계약방법']} | 설계 {amt}원 | {r['공고명']}")
        else:
            amt = f"{r['계약금액원']:,}" if r.get("계약금액원") else "-"
            print(f"[계약/{r['발주유형']}] {r['체결일']} | {r['주관부서'] or '-'}"
                  f" | {r['계약방법']} | {amt}원 | 공고 {r['연결공고번호']}"
                  f" | {r['계약명']} | {r['업체명']}")
