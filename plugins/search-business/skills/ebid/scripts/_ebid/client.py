"""ebid.ex.co.kr(한국도로공사 전자조달시스템) 입찰공고 목록 조회 클라이언트.

이식 원본(읽기 전용): C:\\Project\\ANJ-OFFICE\\biz-renewal\\back\\app\\infra\\integrations\\ebid\\client.py
원본은 이미 FastAPI/DB 의존이 없는 순수 requests 기반 모듈이라 로직은 그대로 옮기고,
standalone 스크립트에서 바로 쓰도록 이 파일 하나로 독립시켰다 (원본과 동일 동작 유지).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://ebid.ex.co.kr"
DEFAULT_PAGE_PATH = "/default.do"
BID_NOTICE_LIST_PATH = "/ui/sp/expro/bidnoti/findListBidNoti.do"
DEFAULT_URL = BASE_URL + DEFAULT_PAGE_PATH
BID_NOTICE_LIST_URL = BASE_URL + BID_NOTICE_LIST_PATH
# 공고 상세의 첨부파일 목록(fileAttList)을 포함한
# "공유 정보" 조회 엔드포인트. chrome-devtools 로 실측(findInfoBidShared.do), 첨부 다운로드
# 역추적 과정에서 발견해 이식. 실측 기록 참고.
FIND_INFO_BID_SHARED_PATH = "/ui/sp/expro/shared/findInfoBidShared.do"
FIND_INFO_BID_SHARED_URL = BASE_URL + FIND_INFO_BID_SHARED_PATH
# 물품(MT) 첨부 다운로드 맹점 조사 추가 — findInfoBidShared.do 가 fileAttList: [] 를 주는
# 물품 공고라도, 이 엔드포인트(입찰결과 상세 화면이 쓰는 API)의 detailData.att_no 에
# 첨부그룹이 걸려있는 경우가 있다. CT/SV 는 반대로 이 엔드포인트의 fileAttList 가 항상
# 빈 배열이었다(§9.3, chrome-devtools 실측) — 즉 발주구분에 따라 첨부가 두 엔드포인트 중
# 어느 쪽에 붙는지가 갈린다. 실측 기록(물품 공고 첨부) 참고.
FIND_INFO_RESULT_DETAIL_PATH = "/ui/sp/expro/bidresult/findInfoResultDetail.do"
FIND_INFO_RESULT_DETAIL_URL = BASE_URL + FIND_INFO_RESULT_DETAIL_PATH
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)
DEFAULT_STATUS = "Z"
DEFAULT_STATUS_CODES = ["EY", "GY", "CB", "FY", "UR"]
NOTICE_CLASS_MENU_CODES = {
    "SV": "NPRO12001",
    "MT": "NPRO13001",
    "CT": "NPRO11001",
}
# findInfoBidShared.do 호출 시 실측된 menucode는 "결과"(*002) 계열이었다
# (입찰결과 상세 페이지에서 재현했기 때문). 공고가 아직 진행 중일 때(입찰공고 페이지 경유)도
# 이 코드가 그대로 통하는지는 미검증 — ebid.md §첨부 다운로드 "열린 질문" 참고.
RESULT_CLASS_MENU_CODES = {
    "SV": "NPRO12002",
    "MT": "NPRO13002",
    "CT": "NPRO11002",
}
CSRF_META_RE = re.compile(r'<meta[^>]+name=["\']_csrf["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
CSRF_HEADER_META_RE = re.compile(
    r'<meta[^>]+name=["\']_csrf_header["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def format_ebid_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip().replace("-", "").replace("/", "").replace(".", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid ebid date: {value}")
    try:
        datetime.strptime(text, "%Y%m%d")  # 20251301 같은 달·일 범위 오류를 서버로 보내지 않는다
    except ValueError as exc:
        raise ValueError(f"invalid ebid date: {value}") from exc
    return text


class EbidClient:
    base_url = BASE_URL

    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 0.8,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.user_agent = user_agent
        self.session = self._build_session()
        self._csrf_token: str | None = None
        self._csrf_header_name = "x-csrf-token"

    def _build_session(self) -> requests.Session:
        retry = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=self.max_retries,
            status=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": self.user_agent})
        return session

    def ensure_csrf_token(self) -> tuple[str, str]:
        if self._csrf_token:
            return self._csrf_header_name, self._csrf_token

        response = self.session.get(DEFAULT_URL, timeout=self.timeout_seconds)
        response.raise_for_status()
        html = response.text
        token_match = CSRF_META_RE.search(html)
        if token_match is None:
            raise RuntimeError("ebid csrf token not found")
        header_match = CSRF_HEADER_META_RE.search(html)
        self._csrf_token = token_match.group(1).strip()
        if header_match is not None and header_match.group(1).strip():
            self._csrf_header_name = header_match.group(1).strip()
        return self._csrf_header_name, self._csrf_token

    def build_search_payload(
        self,
        *,
        notice_class: str,
        from_noti_date: str | None,
        to_noti_date: str | None,
        status: str = DEFAULT_STATUS,
        arr_status: list[str] | None = None,
        payload_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_notice_class = str(notice_class).strip().upper()
        if normalized_notice_class not in NOTICE_CLASS_MENU_CODES:
            raise ValueError(f"unsupported ebid notice_class: {notice_class}")

        # 날짜 None = 기간 필터 없이 조회 (공고번호 단건 조회용 — 서버가 정상 처리, 실측 2026-08-25)
        payload: dict[str, Any] = {
            "to_noti_date": format_ebid_date(to_noti_date) if to_noti_date else None,
            "from_noti_date": format_ebid_date(from_noti_date) if from_noti_date else None,
            "limit_area": [],
            "status": status,
            "arr_status": list(arr_status or DEFAULT_STATUS_CODES),
            "pq_type": None,
            "bid_shpr1": None,
            "plrl_bid_yn": None,
            "dsgng_amt_start": None,
            "dsgng_amt_end": None,
            "cth_limit": None,
            "cnat_pbnt_amt_start": None,
            "cnat_pbnt_amt_end": None,
            "nwtc_ptnt_no1": None,
            "nwtc_ptnt_no2": None,
            "page": "noti",
            "noti_cls": normalized_notice_class,
            "noti_nm": None,
        }
        if payload_overrides:
            payload.update(payload_overrides)
        return payload

    def build_request_log_headers(self, *, notice_class: str) -> dict[str, str]:
        menu_code = self.resolve_menu_code(notice_class)
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "menucode": menu_code,
            "referer": DEFAULT_URL,
            "origin": BASE_URL,
            "x-requested-with": "XMLHttpRequest",
            self._csrf_header_name: "***masked***" if self._csrf_token else "",
            "user-agent": self.user_agent,
        }

    @staticmethod
    def resolve_menu_code(notice_class: str) -> str:
        normalized_notice_class = str(notice_class).strip().upper()
        try:
            return NOTICE_CLASS_MENU_CODES[normalized_notice_class]
        except KeyError as exc:
            raise ValueError(f"unsupported ebid notice_class: {notice_class}") from exc

    def fetch_bid_notice_list(
        self,
        *,
        notice_class: str,
        from_noti_date: str | None,
        to_noti_date: str | None,
        payload_overrides: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], int, str]:
        csrf_header_name, csrf_token = self.ensure_csrf_token()
        payload = self.build_search_payload(
            notice_class=notice_class,
            from_noti_date=from_noti_date,
            to_noti_date=to_noti_date,
            payload_overrides=payload_overrides,
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": DEFAULT_URL,
            "menucode": self.resolve_menu_code(notice_class),
            csrf_header_name: csrf_token,
        }
        response = self.session.post(
            BID_NOTICE_LIST_URL,
            json=payload,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        items = self.extract_items(response.json())
        return items, response.status_code, response.url

    @staticmethod
    def resolve_result_menu_code(notice_class: str) -> str:
        """resolve_menu_code 의 "결과"(*002) 계열 버전 — §RESULT_CLASS_MENU_CODES."""
        normalized_notice_class = str(notice_class).strip().upper()
        try:
            return RESULT_CLASS_MENU_CODES[normalized_notice_class]
        except KeyError as exc:
            raise ValueError(f"unsupported ebid notice_class: {notice_class}") from exc

    def find_info_bid_shared(
        self,
        *,
        noti_id: str,
        noti_cont_id: str,
        noti_no: str,
        bid_no: str | int,
        bid_rev: str | int,
        notice_class: str,
    ) -> dict[str, Any]:
        """공고 상세 "공유정보" 조회.

        findListBidNoti.do(목록) 응답의 식별자 5종만으로 호출 가능하며, 응답의
        `fileAttList` 에 첨부파일 목록(그룹코드·파일ID·저장경로·원본파일명·크기)이 통째로
        들어있다 — 첨부 다운로드(raonk 프로토콜, raonk.py)의 입력이 되는 핵심 조회.
        menucode 는 결과(*002) 계열로 실측되었다 — resolve_result_menu_code 참고.
        """
        csrf_header_name, csrf_token = self.ensure_csrf_token()
        payload = {
            "noti_id": noti_id,
            "noti_cont_id": noti_cont_id,
            "noti_no": noti_no,
            "bid_no": str(bid_no),
            "bid_rev": str(bid_rev),
            "noti_cls": str(notice_class).strip().upper(),
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": DEFAULT_URL,
            "menucode": self.resolve_result_menu_code(notice_class),
            csrf_header_name: csrf_token,
        }
        response = self.session.post(
            FIND_INFO_BID_SHARED_URL,
            json=payload,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("ebid findInfoBidShared response is not a JSON object")
        return data

    def find_info_result_detail(
        self,
        *,
        noti_id: str,
        noti_cont_id: str,
        noti_no: str,
        bid_no: str | int,
        bid_rev: str | int,
        notice_class: str,
        bid_nm: str | None = None,
        rmcn_yn: str | None = None,
    ) -> dict[str, Any]:
        """물품(MT) 첨부 다운로드 맹점 조사 추가 — "입찰결과 상세" 화면이 개찰금액/낙찰업체
        정보와 함께 호출하는 API. chrome-devtools 로 202505444(MT, fileAttList 실재)와
        202603727(CT, 기존에 검증된 findInfoBidShared 경로)을 나란히 실측한 결과:

        - MT: find_info_bid_shared() 의 fileAttList 는 [] (att_no: null), 이 엔드포인트의
          fileAttList 는 3건 채워짐(detailData.att_no 도 실값).
        - CT: 정반대 — find_info_bid_shared() 에 fileAttList 4건, 이 엔드포인트는 [](att_no: null).

        즉 발주구분에 따라 첨부그룹이 두 엔드포인트 중 어느 한쪽에만 걸린다(둘 다 채워지는
        케이스는 실측 안 됨). 그래서 download_attachment.py 는 find_info_bid_shared() 가 빈
        배열을 줄 때만 이 메서드를 폴백으로 호출한다 — CT/SV 는 사실상 호출 안 됨(요청 낭비 없음).

        bid_nm/rmcn_yn 은 실측 트래픽 그대로 맞추려고 넣은 선택 필드다(서버가 실제로
        검증하는지는 미확인) — bid_nm 은 find_info_bid_shared() 응답의 findListBid[0].bid_nm,
        rmcn_yn 은 findListBidNoti.do 응답 항목(물품 전용 필드, ebid.md §5)에서 그대로 전달하면
        된다. 실측 기록(물품 공고 첨부) 참고.
        """
        csrf_header_name, csrf_token = self.ensure_csrf_token()
        payload: dict[str, Any] = {
            "noti_no": noti_no,
            "noti_id": noti_id,
            "noti_cont_id": noti_cont_id,
            "bid_no": str(bid_no),
            "bid_rev": str(bid_rev),
            "noti_cls": str(notice_class).strip().upper(),
            "isCompanyUser": False,
        }
        if bid_nm is not None:
            payload["bid_nm"] = bid_nm
        if rmcn_yn is not None:
            payload["rmcn_yn"] = rmcn_yn
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": DEFAULT_URL,
            "menucode": self.resolve_result_menu_code(notice_class),
            csrf_header_name: csrf_token,
        }
        response = self.session.post(
            FIND_INFO_RESULT_DETAIL_URL,
            json=payload,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("ebid findInfoResultDetail response is not a JSON object")
        return data

    @staticmethod
    def extract_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "rows", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise RuntimeError("ebid response is not a JSON list")

    def describe(self) -> dict[str, str]:
        return {"platform": "ebid", "base_url": self.base_url}
