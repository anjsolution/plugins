"""ebid 계약공개현황 API — 계약명 부분일치 검색(수의·지명경쟁 포함 체결 원장).

입찰공고에 없는 계약을 찾을 때 쓴다. 건별 웹 딥링크는 화면이 파라미터를 읽지 않아 불가.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from .client import BASE_URL, EbidClient

LIST_ENDPOINT = "/ui/sp/expro/cntropen/findListCntrOpn.do"
MENUCODE = "NPRO20001"  # 계약공개현황 조회 화면
DEFAULT_LOOKBACK_DAYS = 1095  # 기간 미지정 시 기본 폭(약 3년). 7년 단일 호출도 동작 실측(2026-08-22)
MAX_RETRIES = 2



def search_contracts(
    client: EbidClient, *, keyword: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    csrf_header, csrf_token = client.ensure_csrf_token()
    response = client.session.post(
        BASE_URL + LIST_ENDPOINT,
        json={"cntr_nm": keyword, "from_yyyymmdd": from_date, "to_yyyymmdd": to_date},
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            csrf_header: csrf_token,
            "Referer": BASE_URL + "/default.do",
            "menucode": MENUCODE,
        },
        timeout=30,
    )
    response.raise_for_status()
    # requests 는 이 응답을 latin-1 로 잘못 추정하므로 반드시 content 를 UTF-8 로 직접 디코드
    data = json.loads(response.content.decode("utf-8"))
    if isinstance(data, list):
        return data
    return next((v for v in data.values() if isinstance(v, list)), [])


