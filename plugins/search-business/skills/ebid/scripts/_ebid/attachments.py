"""공고번호 → 공고 1건 해석, 첨부 목록 조회(물품 폴백 포함), RAONK 다운로드.

- resolve_notice: 발주유형 CT/SV/MT 를 순회해 공고를 찾고 다중 차수면 최신 차수를 돌려준다.
- fetch_attachment_list: findInfoBidShared 가 빈 배열이면 findInfoResultDetail 로 폴백
  (물품 공고는 첨부가 후자에 걸려 있는 서버측 비일관성 실측).
- download_one_attachment: RAONK 전송 + 확장자-시그니처 검증 후 디스크 기록.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

from . import raonk
from .errors import describe_error
from .client import EbidClient
from .search import ALL_NOTICE_CLASSES, STATUS_FILTER_OVERRIDE, resolve_date_window

REQUEST_INTERVAL_SECONDS = 0.25  # 요청 예절: 같은 실행 내 요청 간 최소 간격.
# 1.0 → 0.25. 첨부 40개 다운로드에서 sleep 만 80초였다(총 177초 중). 0 으로 두지 않는 것은
# 사내 배포판이라 여러 직원이 같은 회사 IP 로 동시에 돌릴 수 있어서다 — 여유를 남긴다.
MAX_DOWNLOAD_WORKERS = 4  # 첨부 동시 다운로드 상한
MAX_RETRIES = 2

# 흔한 HWP 시그니처 두 종류. 구버전 HWP(2.x 이하)는 "HWP Document File" 문자열이 파일 앞부분에
# 그대로 박혀있고, HWP 5.x(현재 다수)는 OLE/CFB 컨테이너라 매직 넘버 D0 CF 11 E0 로 시작한다.
_HWP_CFB_MAGIC = b"\xd0\xcf\x11\xe0"
_HWP_LEGACY_MARKER = b"HWP Document File"
_PDF_MAGIC = b"%PDF"
_HTML_SNIFF_MARKERS = (b"<!doctype html", b"<html")



def resolve_notice(
    client: EbidClient,
    notice_no: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any] | None:
    """noti_no 만으로 CT/SV/MT 를 순회하며 공고 1건을 찾는다 (search.py 의 검색 로직 재사용).

    date_from/date_to 를 생략하면 **기간 필터 없이** 조회한다 — 공고번호는 유일키라
    날짜 창이 불필요하고, 서버도 날짜 None 을 정상 처리함(실측 2026-08-25:
    2019·2020년 공고 번호 조회 성공). 명시하면 그 창으로 좁힌다.

    같은 공고번호에 차수(bid_rev)별 행이 여러 개 올 수 있다 — 차수 1 취소(CB) 후
    같은 번호로 재입찰해 차수 2 낙찰(실측 2026-08-27: 201700462·202503233,
    references/ebid-필드사전.md §상태코드). 첫 행을 집으면 취소된 구차수를 최종 상태로 오독하므로
    **최신 차수 행을 반환**하고, 다중 차수 감지 시 stderr 로 알린다.
    """
    if date_from or date_to:
        from_date, to_date = resolve_date_window(date_from, date_to)
    else:
        from_date = to_date = None
    for index, notice_class in enumerate(ALL_NOTICE_CLASSES):
        if index > 0:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        items, _status, _url = client.fetch_bid_notice_list(
            notice_class=notice_class,
            from_noti_date=from_date,
            to_noti_date=to_date,
            payload_overrides={"noti_no": notice_no, "noti_nm": None, "arr_status": STATUS_FILTER_OVERRIDE},
        )
        matches = [item for item in items if str(item.get("noti_no")) == str(notice_no)]
        if matches:
            matches.sort(key=lambda item: int(item.get("bid_rev") or 0))
            if len(matches) > 1:
                revs = ", ".join(
                    f"차수{m.get('bid_rev')}={m.get('prog_sts')}" for m in matches)
                print(f"[ebid] 공고 {notice_no}: 차수별 행 {len(matches)}개 발견"
                      f"({revs}) — 최신 차수를 사용합니다", file=sys.stderr)
            return matches[-1]
    return None


def sniff_file_kind(content: bytes) -> str:
    """다운로드된 바이트가 HWP/PDF 인지, HTML 에러 페이지를 잘못 받은 건 아닌지 판별.

    호출부에서 미리 슬라이스하지 말고 (원본) content 를 그대로 넘길 것 — 필요한 프리픽스
    길이는 이 함수가 알아서 잘라 쓴다(과거에는 호출부가 content[:64] 로 미리 잘라 넘겨서,
    아래 head[:200] 슬라이스가 항상 <=64 바이트만 보게 되는 죽은 코드였다).
    """
    head = content[:200]
    lowered = head.lower()
    if any(marker in lowered for marker in _HTML_SNIFF_MARKERS):
        return "html"
    if head.startswith(_HWP_CFB_MAGIC) or _HWP_LEGACY_MARKER in head[:64]:
        return "hwp"
    if head.startswith(_PDF_MAGIC):
        return "pdf"
    return "unknown"


# 확장자별로 sniff 결과가 이 값이 아니면(=html 오류 페이지를 파일인 척 저장한 흔한 함정)
# 다운로드를 실패로 간주한다. 매핑에 없는 확장자는 검증을 건너뛴다(=unknown 도 허용).
_EXPECTED_SNIFF_BY_EXT = {".hwp": "hwp", ".pdf": "pdf"}


def safe_attachment_filename(raw_name: str) -> str:
    """서버가 내려준 원본 파일명(`orgn_file_nm`)을 디스크 쓰기용으로 정규화한다.

    `Path(raw) / name` 처럼 서버 문자열을 그대로 out_dir 와 이어붙이면, `orgn_file_nm` 이
    `..\\..\\evil.txt` 나 `C:\\Windows\\evil.dll` 같은 값일 때 out_dir 밖에 쓰기가 가능하다
    (pathlib 는 우변이 절대경로면 좌변을 버리고, `..` 세그먼트도 그대로 통과시킨다).

    `PurePath(raw).name` 은 마지막 경로 성분만 남기므로 `..`/절대경로/드라이브 지정이 몇 겹
    중첩됐든 전부 제거된다 — 남는 게 없거나(원본이 ``''``/``'.'``/``'..'``/루트뿐이었던 경우)
    빈 문자열이면 명시적으로 거부한다.
    """
    name = Path(str(raw_name)).name
    if not name or name in {".", ".."}:
        raise ValueError(f"안전하지 않은 첨부파일명(정규화 결과 비어있음): {raw_name!r}")
    # 폴더명은 막으면서 파일명을 안 막을 이유가 없다 — 금지문자·연속공백·끝점을 같은 규칙으로 정리하고
    # 길이를 제한한다(확장자는 보존). ebid 는 지금 정상 파일명을 주지만 그건 서버 사정이다.
    name = re.sub(r"\s+", " ", _FS_FORBIDDEN.sub(" ", name)).strip().rstrip(". ")
    if not name:
        raise ValueError(f"안전하지 않은 첨부파일명(정화 결과 비어있음): {raw_name!r}")
    if len(name) > FILE_NAME_MAX:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = stem[:FILE_NAME_MAX - len(ext) - 1].rstrip(". ") + "." + ext
        else:
            name = name[:FILE_NAME_MAX].rstrip(". ")
    return name


def download_one_attachment(
    client: EbidClient,
    *,
    attachment: dict[str, Any],
    notice_class: str,
    out_dir: Path,
) -> dict[str, Any]:
    raw_filename = attachment["orgn_file_nm"]
    grp_cd = attachment["file_grp_cd"]
    att_id = attachment["file_att_id"]
    expected_size = attachment.get("att_file_siz")

    try:
        # 디스크에 쓸 때 쓰는 이름은 반드시 이 정규화를 거친다 — RAONK 프로토콜 호출(k31 필드)
        # 에는 서버가 원래 준 raw_filename 을 그대로 쓴다(실측 트래픽과 동일하게 유지, 굳이
        # 안 바꿀 이유가 없다). out_dir 밖 쓰기 방지는 오직 디스크 쓰기 경로에서만 필요하다.
        safe_name = safe_attachment_filename(raw_filename)
    except ValueError as exc:
        return {"filename": raw_filename, "종류": "file", "error": str(exc)}

    try:
        content = raonk.fetch_attachment(
            client.session,
            grp_cd=grp_cd,
            att_id=att_id,
            filename=raw_filename,
            notice_class=notice_class,
        )
    except (requests.exceptions.RequestException, raonk.RaonkError) as exc:
        info = describe_error(exc)
        return {"filename": safe_name, "종류": info["종류"], "error": info["메시지"]}

    kind = sniff_file_kind(content)
    expected_kind = _EXPECTED_SNIFF_BY_EXT.get(Path(safe_name).suffix.lower())
    if expected_kind is not None and kind != expected_kind:
        # 흔한 함정: 세션 만료/차단 시 서버가 200 OK 로 HTML 안내 페이지를 돌려주는 경우가
        # 있다 — 파일 확장자가 기대하는 시그니처가 아니면 디스크에 쓰지 않고 실패 처리한다.
        return {
            "filename": safe_name,
            "종류": "server",
            "error": f"시그니처 불일치: 확장자={Path(safe_name).suffix!r} 기대={expected_kind!r} 실제={kind!r}",
            "content_preview": content[:200].decode("utf-8", errors="replace"),
        }

    dest = out_dir / safe_name
    dest.write_bytes(content)
    result: dict[str, Any] = {
        "filename": safe_name,
        "size": len(content),
        "path": str(dest),
        "sniff": kind,
    }
    if raw_filename != safe_name:
        result["filename_raw"] = raw_filename
    if expected_size is not None and len(content) != expected_size:
        result["size_mismatch_expected"] = expected_size
    return result

_FS_FORBIDDEN = re.compile(r'[\\/:*?"<>|\r\n\t]+')
FOLDER_NAME_MAX = 80   # (공고번호)공고명 폴더명 길이 상한 — 윈도우 경로 한계 여유
FILE_NAME_MAX = 100    # 첨부 파일명 길이 상한 (확장자 포함)

def default_folder_name(notice_no: str, notice_name: str) -> str:
    clean = _FS_FORBIDDEN.sub(" ", str(notice_name or "")).strip()
    clean = re.sub(r"\s+", " ", clean).rstrip(". ")
    name = f"({notice_no}){clean}" if clean else f"({notice_no})"
    return name[:FOLDER_NAME_MAX].rstrip(". ")


def fetch_attachment_list(client: EbidClient, notice: dict[str, Any]) -> tuple[list[dict], str]:
    """첨부 목록 조회 — download_attachment.py main() 과 동일한 2단 경로(MT 폴백 포함)."""
    notice_class = notice["noti_cls"]
    shared = client.find_info_bid_shared(
        noti_id=notice["noti_id"], noti_cont_id=notice["noti_cont_id"],
        noti_no=notice["noti_no"], bid_no=notice["bid_no"],
        bid_rev=notice["bid_rev"], notice_class=notice_class,
    )
    attachments = shared.get("fileAttList") or []
    if attachments:
        return attachments, "findInfoBidShared"
    time.sleep(REQUEST_INTERVAL_SECONDS)
    find_list_bid = shared.get("findListBid") or []
    bid_nm = find_list_bid[0].get("bid_nm") if find_list_bid and isinstance(find_list_bid[0], dict) else None
    try:
        detail = client.find_info_result_detail(
            noti_id=notice["noti_id"], noti_cont_id=notice["noti_cont_id"],
            noti_no=notice["noti_no"], bid_no=notice["bid_no"],
            bid_rev=notice["bid_rev"], notice_class=notice_class,
            bid_nm=bid_nm, rmcn_yn=notice.get("rmcn_yn"),
        )
    except Exception as exc:
        info = describe_error(exc)
        print(f"[ebid] 물품 첨부 대체 조회 실패 — 첨부 없음으로 계속: {info['메시지']} [{info['종류']}]",
              file=sys.stderr)
        return [], "findInfoBidShared"
    return detail.get("fileAttList") or [], "findInfoResultDetail"


def pick_workers(sizes: list[Any]) -> int:
    """첨부 크기로 동시 다운로드 수를 정한다.

    큰 파일 소수에는 병렬이 역효과다 — 실측에서 35MB 3파일이 직렬 8.9초, 병렬4 는 12.3초였다
    (같은 대역폭을 나눠 쓰면서 큰 파일이 밀린다). 반대로 작은 파일 다수에는 크게 이득이다
    (10MB 5파일 6.8초 → 3.0초). 그래서 평균 크기로 갈라 준다.
    """
    values = [int(s or 0) for s in sizes]
    if not values:
        return 1
    average = sum(values) / len(values)
    return 2 if average > 10 * 1024 * 1024 else MAX_DOWNLOAD_WORKERS


def existing_download(attachment: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    """이미 받아 둔 파일이면 그 사실을, 아니면 None 을 돌려준다 (`--skip-existing` 판정).

    같은 공고 폴더 안의 **파일명 + 바이트 크기**가 목록의 값과 맞을 때만 건너뛴다. 크기를 보는
    이유는 중간에 끊긴 파일을 완료로 착각하지 않기 위해서다 — 부분 실패 뒤 재실행할 때
    실패한 것만 다시 받는 게 이 옵션의 목적이라 그 판정이 틀리면 쓸모가 없다.
    서버가 크기를 안 주면(0/None) 크기 대조를 못 하므로 비어 있지 않은 파일만 건너뛰고
    그 사실을 `사유` 에 남긴다.
    """
    try:
        name = safe_attachment_filename(attachment["orgn_file_nm"])
    except (ValueError, KeyError):
        return None
    dest = out_dir / name
    if not dest.is_file():
        return None
    actual = dest.stat().st_size
    expected = int(attachment.get("att_file_siz") or 0)
    if expected:
        if actual != expected:
            return None  # 크기가 다르면 중간에 끊긴 것 — 다시 받는다
        return {"filename": name, "size": actual, "사유": "이미 받음"}
    if actual <= 0:
        return None
    return {"filename": name, "size": actual, "사유": "이미 받음(크기 미확인)"}
