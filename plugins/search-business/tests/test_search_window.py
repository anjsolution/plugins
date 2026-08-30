import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

from _ebid.client import format_ebid_date  # noqa: E402
from _ebid.search import NOTICE_CLASS_LABELS, resolve_date_window  # noqa: E402


def test_labels():
    assert NOTICE_CLASS_LABELS == {"공사": "CT", "용역": "SV", "물품": "MT"}


def test_window_default_lookback():
    f, t = resolve_date_window(None, "20260830", lookback_days=365)
    assert t == "20260830"
    assert f == (date(2026, 8, 30) - timedelta(days=365)).strftime("%Y%m%d")


def test_window_explicit():
    assert resolve_date_window("20250701", "20250703", lookback_days=365) == ("20250701", "20250703")


def test_no_project_paths_in_package():
    bad = ("ebid-ttms", "stages/", "data/ebid-raw", "20120101")
    for p in (SCRIPTS / "_ebid").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        for b in bad:
            assert b not in text, f"{p.name} contains {b!r}"


def test_format_ebid_date_accepts_separators_and_rejects_bad_dates():
    import pytest
    assert format_ebid_date("2025-01-01") == "20250101"
    for bad in ("abc", "20251301", "20250132"):
        with pytest.raises(ValueError):
            format_ebid_date(bad)


def test_no_absolute_sibling_imports_anywhere():
    import re
    pat = re.compile(r"^\s*(from (client|search|raonk|contracts|attachments|normalize) import|import (client|raonk|search|contracts|attachments|normalize)\b)", re.M)
    for p in (SCRIPTS / "_ebid").glob("*.py"):
        assert not pat.search(p.read_text(encoding="utf-8")), p.name
