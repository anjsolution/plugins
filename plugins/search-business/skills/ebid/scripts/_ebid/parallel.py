"""동시 요청 — 네트워크 대기(I/O bound)라 스레드 풀로 충분하다.

- MAX_CONCURRENCY 는 서버 예절 상한. CPU·코어 수와 무관.
- 세션(requests.Session)은 호출 전에 CSRF·쿠키를 확보한 뒤 공유한다 — 스레드 시작 후엔
  세션 상태를 바꾸지 않는다(각 요청은 헤더만 붙여 보냄).
- 결과 순서는 입력 순서를 보존한다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

MAX_CONCURRENCY = 4


def map_parallel(
    func: Callable[[T], R], items: Iterable[T], *, max_workers: int = MAX_CONCURRENCY,
) -> list[tuple[R | None, BaseException | None]]:
    """items 마다 func 를 동시에 실행. 반환은 입력 순서대로 (결과, 예외) 쌍 — 한 건의 예외가
    다른 건을 막지 않는다. 호출 측이 예외를 어떻게 다룰지(전체 실패/부분 실패) 정한다."""
    items = list(items)
    if not items:
        return []

    def run(item: T) -> tuple[R | None, BaseException | None]:
        try:
            return func(item), None
        except BaseException as exc:  # noqa: BLE001 — 호출 측에 그대로 넘긴다
            return None, exc

    workers = max(1, min(max_workers, len(items)))
    if workers == 1:
        return [run(items[0])]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, items))
