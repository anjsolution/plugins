import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # anjsolution/


def test_claude_entry():
    m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    e = next(p for p in m["plugins"] if p["name"] == "search-business")
    assert e["source"] == "./plugins/search-business"


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


def test_version_is_same_in_all_three_manifests():
    """버전은 세 곳(Claude·Codex·marketplace)에 있다. 한쪽만 올리면 배포본이 어긋난다.

    테스트가 버전 문자열을 하드코딩하면 올릴 때마다 테스트를 고쳐야 해서 검사 구실을 못 한다.
    지켜야 할 불변식은 값 자체가 아니라 세 값이 서로 같다는 것이다(키워드에서 실제로 어긋났었다).
    """
    import json
    root = Path(__file__).resolve().parents[3]
    plugin_dir = Path(__file__).resolve().parents[1]
    claude = json.loads((plugin_dir / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((plugin_dir / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    entry = next(e for e in market["plugins"] if e["name"] == "search-business")
    assert claude["version"] == codex["version"] == entry["version"], (
        claude["version"], codex["version"], entry["version"])
    assert claude["description"] == codex["description"] == entry["description"]
