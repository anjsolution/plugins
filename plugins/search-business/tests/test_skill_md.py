import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills/ebid/SKILL.md"


def test_frontmatter_and_length():
    text = SKILL.read_text(encoding="utf-8")
    fm = text.split("---")[1]
    assert re.search(r"^name: ebid$", fm, re.M)
    assert "description:" in fm and "공고 검색" in fm
    assert len(text.splitlines()) <= 120


def test_description_is_yaml_safe():
    """description 이 `*` 로 시작하면 YAML 이 앵커 참조로 읽어 프론트매터가 통째로 깨진다.

    깨지면 스킬 목록에 설명 대신 H1 제목이 뜨고 자동 탐색이 아예 동작하지 않는다 — 실제로
    겪었는데 기존 검사(문자열 포함 여부)로는 잡히지 않았다.
    """
    fm = SKILL.read_text(encoding="utf-8").split("---")[1]
    value = re.search(r"^description:\s*(.+)$", fm, re.M).group(1).strip()
    assert value[0] not in "*&!|>%@`{}[]", f"YAML 특수문자로 시작: {value[:20]!r}"


def test_links_all_references_once_level():
    text = SKILL.read_text(encoding="utf-8")
    for f in ("ebid-필드사전.md", "문서-판독-지침.md", "소스-접근성.md"):
        assert f"references/{f}" in text


def test_rules_present():
    text = SKILL.read_text(encoding="utf-8")
    for must in ("최근 1년", "ebid_search_common.py", "ebid_search_contract.py", "--detail", "키워드 없이", "공고번호", "딥링크", "--out", "--list", "kordoc"):
        assert must in text
    assert "20120101" not in text
    assert "제조구매" not in text
    assert "CT/MT" not in text
