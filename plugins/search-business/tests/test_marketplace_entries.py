import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # anjsolution/


def test_claude_entry():
    m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    e = next(p for p in m["plugins"] if p["name"] == "search-business")
    assert e["source"] == "./plugins/search-business" and e["version"] == "0.1.0"


def test_codex_entry():
    m = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    e = next(p for p in m["plugins"] if p["name"] == "search-business")
    assert e["source"] == {"source": "local", "path": "./plugins/search-business"}
    assert e["policy"] == {"installation": "AVAILABLE", "authentication": "ON_USE"}
    assert e["category"] == "Business & Operations"


def test_no_project_remnants_in_plugin():
    # 가드 테스트 자신은 금지 문자열을 패턴으로 갖고 있으므로 tests/ 는 제외한다
    r = subprocess.run(["git", "grep", "-l", "-E", "ebid-ttms|stages/|data/ebid-raw|20120101",
                        "--", "plugins/search-business", ":(exclude)plugins/search-business/tests"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == "", r.stdout
