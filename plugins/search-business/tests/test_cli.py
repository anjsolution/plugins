import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, encoding="utf-8", cwd=cwd)


def test_old_search_script_removed():
    assert not (SCRIPTS / "ebid_search.py").exists()


def test_common_search_bad_date_exit_2(tmp_path):
    r = run("ebid_search_common.py", "--keyword", "x", "--from", "20251301", cwd=tmp_path)
    assert r.returncode == 2 and "날짜" in r.stderr


def test_common_search_help_has_no_2012_and_no_contract_type(tmp_path):
    r = run("ebid_search_common.py", "--help", cwd=tmp_path)
    assert r.returncode == 0 and "20120101" not in r.stdout
    assert "--md" in r.stdout
    assert "계약" not in r.stdout.split("--type")[1].split("--")[0]   # --type 선택지에 계약 없음
    src = (SCRIPTS / "ebid_search_common.py").read_text(encoding="utf-8")
    assert "20120101" not in src and "contracts" not in src


def test_contract_search_bad_date_exit_2(tmp_path):
    r = run("ebid_search_contract.py", "--keyword", "x", "--from", "20251301", cwd=tmp_path)
    assert r.returncode == 2 and "날짜" in r.stderr


def test_contract_search_help_mentions_detail(tmp_path):
    r = run("ebid_search_contract.py", "--help", cwd=tmp_path)
    assert r.returncode == 0
    for opt in ("--detail", "--detail-limit", "--md", "--type"):
        assert opt in r.stdout


def test_fetch_without_out_or_list_exit_2(tmp_path):
    r = run("ebid_fetch.py", "--notice", "202602663", cwd=tmp_path)
    assert r.returncode == 2 and "--out" in r.stderr
    assert list(tmp_path.iterdir()) == []      # 아무것도 만들지 않음


def test_result_docstring_has_no_from_to():
    src = (SCRIPTS / "ebid_result.py").read_text(encoding="utf-8")
    assert "--from" not in src.split('"""')[1]


def test_keyword_optional_on_both_search_clis(tmp_path):
    # 키워드 없이도 인자 단계는 통과해야 한다 — 날짜 오류(2)로 멈추게 해 네트워크를 안 탄다
    for script in ("ebid_search_common.py", "ebid_search_contract.py"):
        r = run(script, "--from", "20251301", cwd=tmp_path)
        assert r.returncode == 2 and "날짜" in r.stderr, script
        h = run(script, "--help", cwd=tmp_path).stdout
        assert "--keyword" in h and "required" not in h.split("--keyword")[1].split("--")[0]


def test_no_keyword_requires_from(tmp_path):
    for script in ("ebid_search_common.py", "ebid_search_contract.py"):
        r = run(script, cwd=tmp_path)                       # 키워드도 --from 도 없음
        assert r.returncode == 2 and "--from" in r.stderr and "--keyword" in r.stderr, script
        r = run(script, "--to", "20260830", cwd=tmp_path)   # --to 만으로는 부족
        assert r.returncode == 2 and "--from" in r.stderr, script
        assert r.stdout == ""                                # 네트워크 호출 전에 멈춤
