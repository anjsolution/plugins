"""CLI 공통 오류 처리 — 예외를 사용자용 한글 메시지 + 종류 코드로 바꾼다.

종류 코드(`종류`)는 스킬·호출 프로젝트가 분기할 때 쓰는 안정된 값이다:
  network  — 서버에 연결 못 함(프록시·샌드박스 차단·타임아웃·DNS)
  http     — 서버가 4xx/5xx 응답
  server   — 연결은 됐지만 응답 내용이 오류/예상 밖 형식
  file     — 파일명·저장 경로 문제(첨부)
  unknown  — 그 밖의 예외
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Any

import requests

NETWORK_HINT = ("ebid.ex.co.kr 에 연결하지 못했습니다 — 네트워크·프록시·샌드박스 차단을 확인하세요. "
                "Codex 샌드박스면 network_access=true 가 필요합니다")
DATE_HINT = "날짜는 YYYYMMDD 8자리(예 20260815, 2026-08-15 도 허용)이며 실제 존재하는 날짜여야 합니다"
NOTICE_NO_HINT = "공고번호는 9자리 숫자입니다 (예 202602664)"


def describe_error(exc: BaseException) -> dict[str, str]:
    """예외 → {"종류": 코드, "메시지": 사용자용 한글}. 원인 예외명은 메시지 끝에 괄호로 남긴다."""
    name = type(exc).__name__
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        status = response.status_code if response is not None else "?"
        return {"종류": "http", "메시지": f"서버가 HTTP {status} 로 응답했습니다"}
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        # ProxyError·SSLError 는 ConnectionError 의 하위
        return {"종류": "network", "메시지": f"{NETWORK_HINT} ({name})"}
    if isinstance(exc, requests.exceptions.RequestException):
        return {"종류": "network", "메시지": f"요청을 보내지 못했습니다 ({name}: {exc})"}
    if name == "RaonkError":
        return {"종류": "server", "메시지": f"첨부 서버(RAONK) 오류: {exc}"}
    if isinstance(exc, RuntimeError):
        return {"종류": "server", "메시지": f"서버 응답을 해석하지 못했습니다: {exc}"}
    if isinstance(exc, (ValueError, OSError)):
        return {"종류": "file", "메시지": str(exc)}
    return {"종류": "unknown", "메시지": f"{name}: {exc}"}


def report_error(prefix: str, exc: BaseException) -> dict[str, str]:
    """stderr 에 `[ebid] {prefix}: 메시지 [종류]` 를 찍고 describe 결과를 돌려준다."""
    info = describe_error(exc)
    print(f"[ebid] {prefix}: {info['메시지']} [{info['종류']}]", file=sys.stderr)
    return info


def is_notice_no(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{9}", str(value or "").strip()))


class KoreanArgumentParser(argparse.ArgumentParser):
    """argparse 의 영어 오류 메시지를 한글로 바꾼다 (종료코드 2 유지)."""

    def error(self, message: str) -> None:  # type: ignore[override]
        m = re.match(r"the following arguments are required: (.+)", message)
        if m:
            text = f"필수 인자가 빠졌습니다: {m.group(1)}"
        else:
            m = re.match(r"argument (\S+): invalid choice: '(.+?)' \(choose from (.+)\)", message)
            if m:
                opt, bad, choices = m.groups()
                text = f"{opt} 값 '{bad}' 은 지원하지 않습니다 (가능: {choices.replace(chr(39), '')})"
            else:
                m = re.match(r"argument (\S+): invalid int value: '(.+)'", message)
                if m:
                    text = f"{m.group(1)} 은 정수여야 합니다 (입력: {m.group(2)})"
                elif message.startswith("unrecognized arguments:"):
                    text = "알 수 없는 인자: " + message.split(":", 1)[1].strip()
                else:
                    text = message
        self.print_usage(sys.stderr)
        self.exit(2, f"[ebid] 인자 오류: {text}\n")
