import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

from _ebid import attachments as at  # noqa: E402


def test_default_folder_name_strips_forbidden_and_truncates():
    name = at.default_folder_name("202602663", 'A/B:C*D?"E<F>G|H')
    assert name.startswith("202602663_")
    assert not any(c in name for c in '\/:*?"<>|')
    long = at.default_folder_name("1", "x" * 200)
    assert len(long) <= 80


def test_default_folder_name_has_no_parentheses_prefix():
    """접두사에 괄호를 쓰면 링크 URL 마다 %28·%29 인코딩이 붙어 읽기 어려워진다."""
    name = at.default_folder_name("202605940", "VMS 통합설치공사")
    assert name == "202605940_VMS 통합설치공사"
    assert not name.startswith("(")
    assert at.default_folder_name("202605940", "") == "202605940"


def test_sniff_kinds():
    assert at.sniff_file_kind(b"%PDF-1.4 ...") == "pdf"
    assert at.sniff_file_kind(b"\xd0\xcf\x11\xe0rest") == "hwp"
    assert at.sniff_file_kind(b"<!doctype html><html>") == "html"


def test_safe_filename_neutralizes_traversal_and_rejects_empty():
    assert at.safe_attachment_filename("../evil.hwp") == "evil.hwp"
    assert at.safe_attachment_filename("C:\Windows\evil.dll") == "evil.dll"
    for bad in ("", ".", ".."):
        with pytest.raises(ValueError):
            at.safe_attachment_filename(bad)
