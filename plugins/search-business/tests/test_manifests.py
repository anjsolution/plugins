import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def _load(rel):
    return json.loads((PLUGIN / rel).read_text(encoding="utf-8"))


def test_claude_manifest():
    m = _load(".claude-plugin/plugin.json")
    assert m["name"] == "search-business"
    assert m["version"] == "0.1.0"
    assert m["author"]["email"] == "khchoi@anjsol.co.kr"


def test_codex_manifest():
    m = _load(".codex-plugin/plugin.json")
    assert m["name"] == "search-business"
    assert m["version"] == "0.1.0"
    assert m["skills"] == "./skills/"
    assert m["interface"]["category"] == "Business & Operations"


def test_requirements_only_requests():
    lines = [l.strip() for l in (PLUGIN / "requirements.txt").read_text().splitlines() if l.strip()]
    assert lines == ["requests"]


def test_skill_tree_exists():
    assert (PLUGIN / "skills/ebid/scripts/_ebid/__init__.py").exists()
    assert (PLUGIN / "skills/ebid/references").is_dir()
