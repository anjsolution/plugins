"""ebid 응답 정규화 — 아는 필드는 한글 키로, 나머지는 원본 그대로 통과(passthrough).

코드→라벨 매핑은 codes.json 한 곳에서 읽는다. 필드 의미·검증 근거는
references/ebid-필드사전.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .client import BASE_URL

CODES: dict[str, Any] = json.loads((Path(__file__).with_name("codes.json")).read_text(encoding="utf-8"))
CLASS_LABEL_BY_CODE: dict[str, str] = CODES["발주유형"]
PROG_STS_EXACT: dict[str, str] = CODES["상태정확"]
PROG_STS_BY_INITIAL: dict[str, str] = CODES["상태첫글자"]
# 계약방법 코드표 = 사이트 공통코드 PE080*/BID_USE_YN (CTA·CTE·CTH·CTL). PE075* 실시간 조회는 빈 응답이라
# 제거했다(2026-08-30 실측) — 새 코드가 passthrough 로 나타나면 PE080 을 다시 조회해 여기에 추가한다.
CPT_TERMS_LABELS: dict[str, str] = CODES["계약방법"]
AREA_LABELS: dict[str, str] = CODES["지역"]
NOTICE_CONSTANT_FIELDS: set[str] = set(CODES["제외필드"])
DEEPLINK_MENU: dict[str, str] = CODES["딥링크메뉴"]


def build_notice_deeplink(item: dict[str, Any]) -> str:
    """공고 화면(em-sp-bid-noti-*)이 상세로 직행하는 조건은 noti_id·noti_cont_id·noti_no·bid_no·bid_rev
    5개 전부 — 하나라도 빠지면 조용히 목록 화면. g2b/part/remicon 은 화면이 읽지 않아 뺐다(2026-08-30 실측)."""
    menu_id = DEEPLINK_MENU.get(item.get("noti_cls") or "")
    if not menu_id or not item.get("noti_id") or not item.get("noti_cont_id"):
        return ""
    return (f"{BASE_URL}/default.do?menuId={menu_id}"
            f"&noti_id={item.get('noti_id')}&noti_cont_id={item.get('noti_cont_id')}"
            f"&noti_no={item.get('noti_no')}&bid_no={item.get('bid_no') or 1}"
            f"&bid_rev={item.get('bid_rev') or 1}")

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

def normalize_notice(item: dict[str, Any], cpt_labels: dict[str, str] | None = None) -> dict[str, Any]:
    """아는 필드만 한글 키로 정규화하고, 나머지 원본 필드는 그대로 통과시킨다.

    화이트리스트 방식은 area(지역) 유실 사고의 원인 — 정규화에
    소비되지 않은 필드는 버리지 않고 원본 키 그대로 덧붙인다. 그래야 API 에
    새 필드가 생겨도 자동으로 노출된다. 제외는 NOTICE_CONSTANT_FIELDS 만.
    """
    cpt_labels = CPT_TERMS_LABELS if cpt_labels is None else cpt_labels
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
        "계약번호": stl,
        "연결공고번호": stl[:-2] if len(stl) > 2 else stl,
        # 주관부서 = 실수요 부서("시설처 전기부" 등) — 계약부서(재무부 류 행정 부서)와 구분
        "주관부서": item.get("svsn_dept_nm"),
        "계약부서": item.get("cntr_dept_nm"),
    }
    consumed = {"noti_cls", "cntr_nm", "cntg_date", "g2b_snd_cpt_terms", "cntr_amt",
                "com_nm", "biz_no", "stl_noti_no", "svsn_dept_nm", "cntr_dept_nm"}
    row.update({k: v for k, v in item.items() if k not in consumed})
    return row

def _join_phone(*parts: Any) -> str:
    return "-".join(str(x) for x in parts if x)


def normalize_contract_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """findInfoCntrOpnDetail 응답(6섹션)을 한글 키 한 겹으로 편다.

    bidInfo·cntrBasInfo 가 없는 건(희망수량 등)은 해당 키가 None/"" 로 남는다.
    필드 근거는 references/ebid-필드사전.md §계약 상세 API.
    """
    opn = detail.get("cntrOpnDetail") or {}
    dept = detail.get("deptAddr") or {}
    bid = detail.get("bidInfo") or {}
    bas = detail.get("cntrBasInfo") or {}
    sw = detail.get("getSwYn") or {}
    vendors = detail.get("repVdInfo") or []
    sd, ed = fmt_dt(opn.get("cntr_sd")), fmt_dt(opn.get("cntr_ed"))
    clause, cause = opn.get("jhhm") or "", opn.get("claus_cd_etc_cause") or ""
    return {
        "계약기간": f"{sd}~{ed}" if sd or ed else "",
        "계약일수": opn.get("cntr_day"),
        "발주처": opn.get("poor") or "",
        "수의근거": " — ".join(x for x in (clause, cause) if x),
        "수의근거코드": opn.get("claus_cd") or "",
        "담당자": dept.get("chr_nm") or "",
        "담당부서전화": _join_phone(dept.get("chr_dept_phone_no1"), dept.get("chr_dept_phone_no2"),
                                   dept.get("chr_dept_phone_no3")),
        "담당부서주소": (dept.get("chr_dept_addr") or "").strip(),
        "담당부서우편번호": _join_phone(dept.get("chr_dept_post_no1"), dept.get("chr_dept_post_no2")),
        "계약업체상세": [{
            "업체명": v.get("vd_nm") or "", "대표자": v.get("rep_nm") or "",
            "주소": (v.get("dtl_addr") or "").strip(), "전화": v.get("phone_no") or "",
            "지분율": v.get("shar_rate") or "",
        } for v in vendors],
        # 아래는 bidInfo / cntrBasInfo — 전자수의 포함 대부분 채워짐, 희망수량은 bidInfo 없음
        "설계금액원": bid.get("dsgng_amt"),
        "예정가격원": bas.get("expt_amt"),
        "개찰일시": fmt_dt(bid.get("open_dt")),
        "경쟁방법": bid.get("cpt_terms_str") or "",
        "제한기준": bid.get("lmtcpt_apply_bas_cd_str") or "",
        "낙찰방법": bid.get("stl_terms_str") or "",
        "PQ": bid.get("pq_type_str") or "",
        "공고명": bas.get("noti_nm") or "",
        "공고일": fmt_dt(bas.get("noti_date")),
        "SW계약여부": sw.get("sw_yn") or "",
    }


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


def _md_escape(text: Any) -> str:
    """마크다운 표 셀·링크 텍스트용 이스케이프 — `|` 와 링크 문법과 충돌하는 `[ ]` 를 보호한다."""
    return str(text or "").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def _biz_no(value: Any) -> str:
    """사업자번호 10자리를 000-00-00000 로. 10자리 숫자가 아니면 원문 그대로."""
    digits = str(value or "").strip()
    if len(digits) == 10 and digits.isdigit():
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return digits or "-"


def _amount(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else (str(value) if value else "-")


def _table_title(label: str, keyword: str, period_label: str, n: int) -> str:
    if not keyword:
        what = "전체 계약" if label == "계약" else "전체 공고"
        return f"### [{label}] {what} ({period_label}, {n}건)\n"
    return f"### [{label}] '{keyword}' 검색 결과 ({period_label}, {n}건)\n"


def _empty_line(keyword: str, period_label: str) -> str:
    return (f"'{keyword}' 검색 결과 없음 ({period_label})." if keyword
            else f"검색 결과 없음 ({period_label}, 키워드 없음).")


def render_notice_markdown(rows: list[dict[str, Any]], *, keyword: str, period_label: str) -> str:
    """입찰공고 검색 결과 → 발주유형(공사·용역·물품)별 표. 공고명은 딥링크를 건 마크다운 링크."""
    out: list[str] = []
    for label in ("공사", "용역", "물품"):
        group = [r for r in rows if r.get("발주유형") == label]
        if not group:
            continue
        out.append(_table_title(label, keyword, period_label, len(group)))
        out.append("| 공고번호 | 지역 | 공고명 | 설계금액 | 계약방법 | 공고일 | 상태 |")
        out.append("|---|---|---|---:|---|---|---|")
        for r in group:
            name = _md_escape(r.get("공고명"))
            link = f"[{name}]({r['딥링크']})" if r.get("딥링크") else name
            out.append(f"| {r.get('공고번호')} | {_md_escape(r.get('지역'))} | {link} | {_amount(r.get('설계금액원'))}"
                       f" | {_md_escape(r.get('계약방법'))} | {r.get('공고일')} | {_md_escape(r.get('상태'))} |")
        out.append("")
    if not out:
        out.append(_empty_line(keyword, period_label))
    return "\n".join(out).rstrip() + "\n"


def render_contract_markdown(rows: list[dict[str, Any]], *, keyword: str, period_label: str,
                             detail: bool = False) -> str:
    """계약공개현황 검색 결과 → 단일 표. detail=True 면 `상세` 키의 항목을 열로 덧붙인다."""
    if not rows:
        return _empty_line(keyword, period_label) + "\n"
    out = [_table_title("계약", keyword, period_label, len(rows))]
    if detail:
        out.append("| 구분 | 공고번호 | 계약명 | 계약방법 | 계약업체 | 대표자 | 총계약금액 | 예정가격 | 체결일"
                   " | 계약기간 | 발주처 | 담당자 | 수의근거 |")
        out.append("|---|---|---|---|---|---|---:|---:|---|---|---|---|---|")
    else:
        out.append("| 구분 | 공고번호 | 계약명 | 계약방법 | 사업자번호 | 계약업체 | 총계약금액 | 체결일 |")
        out.append("|---|---|---|---|---|---|---:|---|")
    for r in rows:
        head = (f"| {_md_escape(r.get('발주유형'))} | {r.get('연결공고번호') or '-'} | {_md_escape(r.get('계약명'))}"
                f" | {_md_escape(r.get('계약방법'))}")
        if not detail:
            out.append(f"{head} | {_biz_no(r.get('사업자번호'))} | {_md_escape(r.get('업체명'))}"
                       f" | {_amount(r.get('계약금액원'))} | {r.get('체결일')} |")
            continue
        d = r.get("상세") or {}
        reps = ", ".join(f"{v['대표자']}({v['지분율']})" if v.get("지분율") else v["대표자"]
                         for v in d.get("계약업체상세") or [] if v.get("대표자"))
        contact = d.get("담당자") or ""
        if d.get("담당부서전화"):
            contact = f"{contact} ({d['담당부서전화']})".strip()
        out.append(f"{head} | {_md_escape(r.get('업체명'))} | {_md_escape(reps) or '-'}"
                   f" | {_amount(r.get('계약금액원'))} | {_amount(d.get('예정가격원'))} | {r.get('체결일')}"
                   f" | {d.get('계약기간') or '-'} | {_md_escape(d.get('발주처')) or '-'} | {_md_escape(contact) or '-'}"
                   f" | {_md_escape(d.get('수의근거')) or '-'} |")
    out.append("")
    return "\n".join(out).rstrip() + "\n"
