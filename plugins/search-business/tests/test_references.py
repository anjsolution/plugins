import re
from pathlib import Path

REF = Path(__file__).resolve().parents[1] / "skills/ebid/references"
BAD = ("ebid-ttms", "stages/", "data/ebid-raw", "scripts/ebid/", "20120101",
       "종합관리", "스키마-명세", "T1", "T5", "T6", "S1", "S4", "관리동", "TTMS", "터널사전")


def test_three_files_exist():
    assert {p.name for p in REF.glob("*.md")} == {"ebid-필드사전.md", "문서-판독-지침.md", "소스-접근성.md"}


def test_no_project_leak():
    for p in REF.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        for b in BAD:
            assert b not in text, f"{p.name}: {b}"


def test_long_files_have_toc():
    for p in REF.glob("*.md"):
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > 100:
            head = "\n".join(lines[:15])
            assert re.search(r"^## (목차|Contents)", head, re.M), f"{p.name} needs TOC"


def test_no_ct_mt_jargon_in_prose():
    # 코드 표기(`CT`)는 허용, 산문 속 "CT/MT" 금지
    for p in REF.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        assert "CT/MT" not in text and "MT/CT" not in text, p.name
