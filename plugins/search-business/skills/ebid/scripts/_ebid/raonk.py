"""ebid.ex.co.kr 첨부파일 다운로드 프로토콜(RAONK Upload/Download) 재구현.

이 사이트의 첨부파일 다운로드는 일반적인 `GET /파일경로` 가 아니라, 라온케이(RAONK)
사의 "웹 파일 전송 컴포넌트"를 통해 이뤄진다. 브라우저는 아래 두 단계를 거친다:

1. `POST /raonkDownload/process.dx?raonk=<세션토큰>` (명령 c10) — 그룹코드(grp_cd)와
   파일ID(att_id)로 서버 내부 저장 경로를 "해석(resolve)"한다. 응답으로 실제 저장 경로와
   파일 크기를 받는다.
2. `GET /raonkDownload/process.dx?k00=...&raonk=<세션토큰>` (명령 c11) — 1번에서 받은
   경로를 그대로 되돌려 보내면 서버가 파일 바이트를 스트리밍한다.

모든 요청/응답 페이로드는 평문 파라미터를 `\\x0b`(unit separator)/`\\x0c`(field separator)로
구분한 문자열로 이어붙인 뒤, 표준 base64 인코딩 + 고정 위치에 리터럴 문자 7개를 끼워넣는
"난독화"(진짜 암호화 아님)를 거쳐 `k00` 파라미터 하나로 전달된다.

## 역추적 방법
chrome-devtools MCP 로 실제 다운로드를 1회 수행하며 `network` 요청을 캡처하고,
서버가 내려준 `raonkupload.base64.js`(원본, 난독화 없음)를 같은 방식으로 fetch 해
`RaonKBase64.makeEncryptParam`/`makeDecryptReponseMessage` 함수 정의를 그대로 읽었다:

```js
makeEncryptParam: function(b) {
    b = RaonKBase64.encode(b);          // 표준 base64 (UTF-8 안전 버전)
    b = RaonKBase64.insertAt(b, 8, "r");
    b = RaonKBase64.insertAt(b, 6, "a");
    b = RaonKBase64.insertAt(b, 9, "o");
    b = RaonKBase64.insertAt(b, 7, "n");
    b = RaonKBase64.insertAt(b, 8, "w");
    b = RaonKBase64.insertAt(b, 6, "i");
    b = RaonKBase64.insertAt(b, 9, "z");
    return b.replace(/[+]/g, "%2B");
}
```

캡처한 실제 요청/응답 바이트를 이 알고리즘의 역함수로 디코딩해 평문 TLV 구조
(`kc\x0cc10\x0bk01\x0c1\x0bk05\x0c1\x0bk31\x0c<파일명>\x0bk21\x0c<JSON 컨텍스트>\x0bk30\x0c<grp_cd>\x0bk16\x0c`
등)를 확인했고, 그 구조를 그대로 이 모듈에서 재현한다. "URL 암호화"는 사이트 UI의 표시
문구일 뿐 실제로는 대칭·비밀키가 전혀 없는 위치 기반 문자열 삽입이다(makeEncryptParam2 라는
CryptoJS/AES 버전도 존재하지만, 이 사이트의 설정(`encryptParam` 설정값)은 1단계 방식을 쓴다 —
실측 캡처가 전부 `k00=`로 시작했고 `k01=`(AES 버전 파라미터명)은 관측되지 않았다).

세부 근거: ebid 첨부 다운로드 실측 기록.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import requests

BASE_URL = "https://ebid.ex.co.kr"
DOWNLOAD_ENDPOINT = f"{BASE_URL}/raonkDownload/process.dx"

# 요청 예절: 프로젝트 전역 정책("요청 간 1초")을 raonk 호출 자체에도 강제한다. c10(경로 해석)과
# c11(실제 다운로드)이 fetch_attachment() 안에서 연달아 발사되던 문제를 코드 리뷰로 지적받고
# 추가함 — 이전에는 download_attachment.py 의 "첨부 파일 간" 1초 대기만 있었고, 첨부 1건 내부의
# c10→c11 사이에는 간격이 없었다.
REQUEST_INTERVAL_SECONDS = 1.0

_UNIT_SEP = "\x0b"  # RaonKBase64._trans_unitDelimiter
_FIELD_SEP = "\x0c"  # RaonKBase64._trans_unitAttributeDelimiter

# makeEncryptParam 의 insertAt 호출 순서 그대로: (index, char). 각 삽입은 "직전 삽입까지
# 반영된" 문자열 기준 인덱스라 순서를 바꾸면 안 된다. 다섯 번째까지 진행하면 문자열 어딘가에
# "raonwiz" 가 흩뿌려진 형태가 된다(문자 그대로 라온케이 사명 이니셜).
_INSERTIONS: list[tuple[int, str]] = [
    (8, "r"),
    (6, "a"),
    (9, "o"),
    (7, "n"),
    (8, "w"),
    (6, "i"),
    (9, "z"),
]
# 디코딩(makeDecryptReponseMessage 의 비-AES 분기)은 삽입의 역순으로 각 위치 문자를 제거한다.
_REMOVALS: list[int] = [9, 6, 8, 7, 9, 6, 8]


def encode_param(plaintext: bytes) -> str:
    """RaonKBase64.makeEncryptParam(plaintext) 의 Python 재현."""
    encoded = base64.b64encode(plaintext).decode("ascii")
    for idx, ch in _INSERTIONS:
        encoded = encoded[:idx] + ch + encoded[idx:]
    return encoded.replace("+", "%2B")


def decode_param(value: str) -> bytes:
    """RaonKBase64.makeDecryptReponseMessage(value) 의 Python 재현 (비-AES 분기만)."""
    value = value.replace(" ", "").replace("\r", "").replace("\n", "").replace("%2B", "+")
    for idx in _REMOVALS:
        value = value[:idx] + value[idx + 1 :]
    padding = (-len(value)) % 4
    value += "=" * padding
    return base64.b64decode(value)


def _strip_raonk_wrapper(text: str) -> str:
    """`<RAONK>...</RAONK>` 래퍼 제거 (RaonKBase64.parseDataFromServer 재현)."""
    lower = text.lower()
    start = lower.find("<raonk>")
    if start != -1:
        text = text[start + len("<raonk>") :]
        lower = text.lower()
    end = lower.find("</raonk>")
    if end != -1:
        text = text[:end]
    return text


def build_tlv(command: str, fields: list[tuple[str, str]]) -> bytes:
    """`kc\\x0c<command>\\x0bk01\\x0c1\\x0b...` 형태의 평문 TLV 바이트열을 조립한다."""
    parts = [f"kc{_FIELD_SEP}{command}"]
    for key, value in fields:
        parts.append(f"{key}{_FIELD_SEP}{value}")
    return _UNIT_SEP.join(parts).encode("utf-8")


def new_transfer_token() -> str:
    """makeGuid() 재현 — 32자리 소문자 hex. 서버 검증 대상이 아닌 클라이언트 상관관계 ID로
    판단(진행률 폴링용, c11/c15 에서만 등장하고 c10 응답 검증에는 쓰이지 않음) — 값 자체의
    생성 알고리즘(makeGuid 원본 구현)은 난독화가 심해 끝까지 추적하지 않고 무작위 hex로 대체."""
    return uuid.uuid4().hex


def _menu_context(*, menu_cd: str, menu_url: str, menu_nm: str, att_id: str) -> str:
    ctx = {
        "usr_id": "GUEST",
        "usr_cls": "N",
        "sys_id": "NEBID",
        "menu_cd": menu_cd,
        "menu_url": menu_url,
        "menu_nm": menu_nm,
        "att_id": att_id,
    }
    # 실측 페이로드가 공백 없는 compact JSON이었다(JS JSON.stringify 기본 동작) — 그대로 맞춘다.
    return json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))


class RaonkError(RuntimeError):
    """raonkDownload/process.dx 가 [OK] 이외의 응답을 준 경우."""


def resolve_attachment_path(
    session: requests.Session,
    *,
    grp_cd: str,
    att_id: str,
    filename: str,
    menu_cd: str,
    menu_url: str,
    menu_nm: str,
    timeout_seconds: int = 30,
) -> tuple[str, int, str]:
    """명령 c10 — grp_cd/att_id 를 서버 내부 저장 경로+크기로 해석한다.

    Returns: (resolved_path, size_bytes, raonk_session_token)
    """
    raonk_token = new_transfer_token()
    json_ctx = _menu_context(menu_cd=menu_cd, menu_url=menu_url, menu_nm=menu_nm, att_id=att_id)
    tlv = build_tlv(
        "c10",
        [
            ("k01", "1"),
            ("k05", "1"),
            ("k31", filename),
            ("k21", json_ctx),
            ("k30", grp_cd),
            ("k16", ""),
        ],
    )
    k00 = encode_param(tlv)
    response = session.post(
        DOWNLOAD_ENDPOINT,
        params={"raonk": raonk_token},
        data=f"k00={k00}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": f"{BASE_URL}/default.do",
            "Origin": BASE_URL,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    body = _strip_raonk_wrapper(response.text)
    if not body.startswith("[OK]"):
        raise RaonkError(f"raonkDownload c10 실패 응답: {body!r}")
    decoded = decode_param(body[len("[OK]") :]).decode("utf-8")
    path_str, size_str = decoded.split(_UNIT_SEP)
    return path_str, int(size_str), raonk_token


def download_attachment_bytes(
    session: requests.Session,
    *,
    resolved_path: str,
    filename: str,
    menu_cd: str,
    menu_url: str,
    menu_nm: str,
    att_id: str,
    raonk_token: str,
    timeout_seconds: int = 60,
) -> requests.Response:
    """명령 c11 — c10 이 돌려준 경로로 실제 파일 바이트를 GET 한다 (스트리밍 응답 반환)."""
    json_ctx = _menu_context(menu_cd=menu_cd, menu_url=menu_url, menu_nm=menu_nm, att_id=att_id)
    tlv = build_tlv(
        "c11",
        [
            ("k01", "1"),
            ("k12", new_transfer_token()),
            ("k05", "1"),
            ("k26", resolved_path),
            ("k31", filename),
            ("k21", json_ctx),
            ("k16", ""),
        ],
    )
    k00 = encode_param(tlv)
    url = f"{DOWNLOAD_ENDPOINT}?k00={k00}&raonk={raonk_token}"
    response = session.get(
        url,
        headers={"Referer": f"{BASE_URL}/default.do"},
        timeout=timeout_seconds,
        stream=True,
    )
    response.raise_for_status()
    return response


def fetch_attachment(
    session: requests.Session,
    *,
    grp_cd: str,
    att_id: str,
    filename: str,
    notice_class: str,
    timeout_seconds: int = 60,
) -> bytes:
    """c10(경로 해석) + c11(다운로드) 을 순서대로 실행해 파일 바이트를 반환하는 헬퍼.

    menu_cd/menu_url/menu_nm 은 notice_class 로부터 "결과(*002)" 페이지 컨텍스트를
    구성한다 — 이 다운로드가 실측된 화면(입찰결과 상세)과 동일한 값. 열린 공고(입찰공고
    상세)에서도 이 컨텍스트가 통하는지는 미검증 — ebid.md 참고.
    """
    from .client import RESULT_CLASS_MENU_CODES  # 지연 임포트 (순환 임포트 회피)

    normalized_class = str(notice_class).strip().upper()
    menu_url_map = {
        "SV": "ui/sp/expro/bidresult/em-sp-bid-result-sv.html",
        "CT": "ui/sp/expro/bidresult/em-sp-bid-result-ct.html",
        "MT": "ui/sp/expro/bidresult/em-sp-bid-result-mt.html",
    }
    menu_nm_map = {"SV": "입찰결과(용역)", "CT": "입찰결과(공사)", "MT": "입찰결과(물품)"}
    try:
        menu_cd = RESULT_CLASS_MENU_CODES[normalized_class]
        menu_url = menu_url_map[normalized_class]
        menu_nm = menu_nm_map[normalized_class]
    except KeyError as exc:
        # 호출부(download_attachment.py)가 requests 예외/RaonkError 만 잡으므로, 여기서도
        # bare KeyError 를 그대로 흘리면 첨부 1건 실패가 전체 CLI 크래시로 번진다 — 명시적으로
        # RaonkError 로 변환해 "이 첨부만 실패 처리"되도록 한다. notice_class 는 실제로는 항상
        # findListBidNoti.do 가 돌려준 CT/SV/MT 이므로 발생 안 하는 게 정상이지만 방어적으로 처리.
        raise RaonkError(f"지원하지 않는 notice_class: {notice_class!r}") from exc

    resolved_path, expected_size, raonk_token = resolve_attachment_path(
        session,
        grp_cd=grp_cd,
        att_id=att_id,
        filename=filename,
        menu_cd=menu_cd,
        menu_url=menu_url,
        menu_nm=menu_nm,
        timeout_seconds=timeout_seconds,
    )
    time.sleep(REQUEST_INTERVAL_SECONDS)  # 요청 예절: c10(경로 해석) → c11(다운로드) 사이 1초
    response = download_attachment_bytes(
        session,
        resolved_path=resolved_path,
        filename=filename,
        menu_cd=menu_cd,
        menu_url=menu_url,
        menu_nm=menu_nm,
        att_id=att_id,
        raonk_token=raonk_token,
        timeout_seconds=timeout_seconds,
    )
    content = response.content
    # `expected_size` 는 int(0 이상)라 falsy 체크(`if expected_size and ...`)를 쓰면 서버가
    # 정말 0바이트 파일 크기를 알려준 엣지 케이스에서 크기 불일치 검증이 조용히 스킵된다 —
    # `is not None` 으로 명시해 0 도 정상적으로 검증 대상에 포함시킨다.
    if expected_size is not None and len(content) != expected_size:
        raise RaonkError(
            f"다운로드 크기 불일치: 서버가 c10 에서 알려준 크기={expected_size}, "
            f"실제 수신={len(content)} (파일명={filename!r})"
        )
    return content
