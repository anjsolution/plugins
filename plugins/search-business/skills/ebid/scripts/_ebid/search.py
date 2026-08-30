"""ebid 입찰공고 목록 API — 발주유형별 검색과 날짜 창 계산.

상태 필터를 비워 개찰 완료 건까지 포함해 검색한다(사이트 UI 기본 필터는 진행 중만 남김).
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any


from .client import EbidClient, format_ebid_date

NOTICE_CLASS_LABELS: dict[str, str] = {"공사": "CT", "용역": "SV", "물품": "MT"}
ALL_NOTICE_CLASSES: tuple[str, ...] = ("CT", "SV", "MT")
DEFAULT_LOOKBACK_DAYS = 1095  # 기간 미지정 시 기본 폭(약 3년). 서버 상한은 미확인
REQUEST_INTERVAL_SECONDS = 1.0  # 요청 예절: 같은 실행 내 요청 간 최소 간격
MAX_RETRIES = 2  # 요청 예절: 재시도 최대 2회 (EbidClient 내부 urllib3 Retry 에 위임)

# client.py 의 build_search_payload 기본값(arr_status=["EY","GY","CB","FY","UR"])은
# "공고중/취소/재입찰" 등 진행 중 단계만 남기는 사이트 UI의 "상태" 체크박스 필터다.
# 실검증 중 발견: 공고 후 시간이 지나 개찰이 끝난 건은 prog_sts 가 이 목록 밖 값(예: "UB")으로
# 바뀌어 있어 기본값으로는 아예 검색되지 않는다. 이 CLI 는 "지금 공고중인 것"이 아니라
# "과거 포함 전체 이력 검색"이 목적이므로, arr_status 를 빈 배열로 덮어써 상태 필터 자체를 끈다.
STATUS_FILTER_OVERRIDE: list[str] = []



def _parse_yyyymmdd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def resolve_date_window(
    date_from: str | None, date_to: str | None, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> tuple[str, str]:
    """--from/--to 문자열을 ebid 포맷(YYYYMMDD) 으로 정규화하고, 생략된 값을 기본값으로 채운다.

    lookback_days: --from 생략 시 종료일에서 거슬러 올라갈 일수. 대화형 키워드 검색
    (ebid_search.py)은 최근 1년로 좁혀 쓴다. 공고번호 단건 조회(resolve_notice)는
    날짜를 아예 안 보내는 방식이라 이 함수를 명시 지정 시에만 쓴다.
    """
    to_date_obj = _parse_yyyymmdd(format_ebid_date(date_to)) if date_to else date.today()
    resolved_to = format_ebid_date(to_date_obj)
    if date_from:
        resolved_from = format_ebid_date(date_from)
    else:
        resolved_from = format_ebid_date(to_date_obj - timedelta(days=lookback_days))
    return resolved_from, resolved_to


def resolve_notice_classes(notice_class_label: str | None) -> tuple[str, ...]:
    if notice_class_label is None:
        return ALL_NOTICE_CLASSES
    return (NOTICE_CLASS_LABELS[notice_class_label],)


def search_bid_notices(
    client: EbidClient,
    *,
    keyword: str,
    from_noti_date: str,
    to_noti_date: str,
    notice_classes: tuple[str, ...],
) -> list[dict[str, Any]]:
    """notice_classes 를 순회하며 키워드로 공고 목록을 조회하고 하나의 리스트로 합친다."""
    results: list[dict[str, Any]] = []
    for index, notice_class in enumerate(notice_classes):
        if index > 0:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        items, _status, _url = client.fetch_bid_notice_list(
            notice_class=notice_class,
            from_noti_date=from_noti_date,
            to_noti_date=to_noti_date,
            payload_overrides={"noti_nm": keyword, "arr_status": STATUS_FILTER_OVERRIDE},
        )
        results.extend(items)
    return results


