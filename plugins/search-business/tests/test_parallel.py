import sys
import threading
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

from _ebid.parallel import MAX_CONCURRENCY, map_parallel  # noqa: E402


def test_order_preserved_and_exceptions_captured():
    def f(x):
        if x == 2:
            raise ValueError("boom")
        time.sleep(0.05 * (3 - x))  # 뒤 항목이 먼저 끝나도 순서는 입력 순
        return x * 10
    out = map_parallel(f, [0, 1, 2, 3])
    assert [r for r, _ in out] == [0, 10, None, 30]
    assert isinstance(out[2][1], ValueError) and all(e is None for i, (_, e) in enumerate(out) if i != 2)


def test_runs_concurrently_but_bounded():
    active, peak, lock = 0, 0, threading.Lock()
    def f(_):
        nonlocal active, peak
        with lock:
            active += 1; peak = max(peak, active)
        time.sleep(0.1)
        with lock:
            active -= 1
    t = time.perf_counter(); map_parallel(f, range(8)); dt = time.perf_counter() - t
    assert peak <= MAX_CONCURRENCY and peak >= 2
    assert dt < 0.8  # 순차면 0.8s 이상


def test_empty_and_single():
    assert map_parallel(lambda x: x, []) == []
    assert map_parallel(lambda x: x + 1, [1]) == [(2, None)]
