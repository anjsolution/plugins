import sys
from pathlib import Path

import requests

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

from _ebid import errors  # noqa: E402
from _ebid.raonk import RaonkError  # noqa: E402


def _http_error(status):
    resp = requests.Response()
    resp.status_code = status
    return requests.exceptions.HTTPError(response=resp)


def test_describe_error_kinds():
    assert errors.describe_error(_http_error(500)) == {"종류": "http", "메시지": "서버가 HTTP 500 로 응답했습니다"}
    net = errors.describe_error(requests.exceptions.ProxyError("x"))
    assert net["종류"] == "network" and "ebid.ex.co.kr" in net["메시지"] and "Codex" in net["메시지"]
    assert errors.describe_error(requests.exceptions.ReadTimeout("t"))["종류"] == "network"
    srv = errors.describe_error(RuntimeError("계약 상세 조회 실패"))
    assert srv["종류"] == "server" and "계약 상세 조회 실패" in srv["메시지"]
    assert errors.describe_error(RaonkError("c10 실패"))["종류"] == "server"
    assert errors.describe_error(ValueError("안전하지 않은 첨부파일명"))["종류"] == "file"
    assert errors.describe_error(KeyError("noti_id"))["종류"] == "unknown"


def test_report_error_prints_kind(capsys):
    info = errors.report_error("검색 실패", requests.exceptions.ConnectionError("boom"))
    err = capsys.readouterr().err
    assert err.startswith("[ebid] 검색 실패: ") and err.rstrip().endswith("[network]")
    assert info["종류"] == "network"


def test_is_notice_no():
    assert errors.is_notice_no("202602664") and errors.is_notice_no(" 202602664 ")
    for bad in ("abc", "2026026", "20260266401", "", None):
        assert not errors.is_notice_no(bad)
