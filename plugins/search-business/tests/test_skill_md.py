import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills/ebid/SKILL.md"


def test_frontmatter_and_length():
    text = SKILL.read_text(encoding="utf-8")
    fm = text.split("---")[1]
    assert re.search(r"^name: ebid$", fm, re.M)
    assert "description:" in fm and "공고 검색" in fm
    assert len(text.splitlines()) <= 120


def test_links_all_references_once_level():
    text = SKILL.read_text(encoding="utf-8")
    for f in ("ebid-필드사전.md", "문서-판독-지침.md", "소스-접근성.md"):
        assert f"references/{f}" in text


def test_rules_present():
    text = SKILL.read_text(encoding="utf-8")
    for must in ("최근 1년", "ebid_search_common.py", "ebid_search_contract.py", "--detail", "공고번호", "딥링크", "--out", "--list", "kordoc"):
        assert must in text
    assert "20120101" not in text
    assert "제조구매" not in text
    assert "CT/MT" not in text
