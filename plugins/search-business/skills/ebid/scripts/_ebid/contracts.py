"""ebid 계약공개현황 API — 계약명 부분일치 검색(수의·지명경쟁 포함 체결 원장) + 건별 상세.

입찰공고에 없는 계약을 찾을 때 쓴다. 건별 웹 딥링크는 화면(`em-sp-cntr-open`)이
URL 파라미터를 읽지 않아 불가 — 조회 화면 진입은 `default.do?menuId=NPRO20001` 까지.
API 세부·필드 근거는 references/ebid-필드사전.md §계약공개현황.
"""

from __future__ import annotations

import json
from typing import Any

from .client import BASE_URL, EbidClient

LIST_ENDPOINT = "/ui/sp/expro/cntropen/findListCntrOpn.do"
DETAIL_ENDPOINT = "/ui/sp/expro/cntropen/findInfoCntrOpnDetail.do"
MENUCODE = "NPRO20001"  # 계약공개현황 조회 화면
CONTRACT_PAGE_URL = f"{BASE_URL}/default.do?menuId={MENUCODE}"  # 비로그인(GUEST) 조회 화면
DEFAULT_LOOKBACK_DAYS = 1095  # 기간 미지정 시 기본 폭(약 3년). 7년 단일 호출도 동작 실측(2026-08-22)
DEFAULT_DETAIL_LIMIT = 30  # --detail 은 건당 1요청 — 기본 상한
MAX_RETRIES = 2


def _headers(client: EbidClient) -> dict[str, str]:
    csrf_header, csrf_token = client.ensure_csrf_token()
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        csrf_header: csrf_token,
        "Referer": CONTRACT_PAGE_URL,
        "menucode": MENUCODE,
    }


def _post_json(client: EbidClient, path: str, body: dict[str, Any]) -> Any:
    response = client.session.post(BASE_URL + path, json=body, headers=_headers(client), timeout=30)
    response.raise_for_status()
    # requests 는 이 응답을 latin-1 로 잘못 추정하므로 반드시 content 를 UTF-8 로 직접 디코드
    return json.loads(response.content.decode("utf-8"))


def search_contracts(
    client: EbidClient, *, keyword: str | None, from_date: str, to_date: str,
    notice_class: str | None = None,
) -> list[dict[str, Any]]:
    """계약명 부분일치 + 체결일 범위 검색. notice_class(CT/SV/MT)는 서버 `gubun` 필터.

    keyword 가 없으면 `cntr_nm` 을 본문에서 빼고 보낸다(기간 내 전체). 화면과 같은 동작이며
    빈 문자열을 보낸 것과 결과가 같다(실측 2026-08-30, 1개월 343건).

    화면(`es-sp-cntr-open-list`)이 보내는 검색 파라미터: cntr_nm · from/to_yyyymmdd · gubun(발주유형)
    · method(계약방법 CTA/CTE/CTH/CTL) · stl_noti_no(계약번호 정확일치). 실측 2026-08-30.
    """
    body: dict[str, Any] = {"from_yyyymmdd": from_date, "to_yyyymmdd": to_date}
    if keyword:
        body["cntr_nm"] = keyword
    if notice_class:
        body["gubun"] = notice_class
    data = _post_json(client, LIST_ENDPOINT, body)
    if isinstance(data, list):
        return data
    return next((v for v in data.values() if isinstance(v, list)), [])


def fetch_contract_detail(client: EbidClient, item: dict[str, Any]) -> dict[str, Any]:
    """목록 행 **전체**를 body 로 보낸다(화면 동작과 동일).

    `cntr_id` 만 보내면 `bidInfo`/`cntrBasInfo` 가 null 로 온다. 전체 행을 보내면 일반·제한·지명·전자수의
    전부 채워지고, `희망수량` 만 `bidInfo` 가 null (표본 15건, 실측 2026-08-30).
    """
    data = _post_json(client, DETAIL_ENDPOINT, item)
    if not isinstance(data, dict):
        raise RuntimeError("계약 상세 응답 형식 오류")
    if data.get("result_status") == "E":
        raise RuntimeError(data.get("result_message") or "계약 상세 조회 실패")
    return data
