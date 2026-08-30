"""ebid 계약공개현황 검색 — 체결된 계약(수의·지명경쟁 포함)을 계약명 키워드로 찾는다.

입찰공고 검색은 별도 도구 ebid_search_common.py. 결과는 한글 키로 정규화한 JSON 배열(stdout).
--md 는 대화창용 표, --table 은 한 줄 표. 진단은 stderr.

    python <스킬폴더>/scripts/ebid_search_contract.py --keyword "터널관리" --from 20190101
    python <스킬폴더>/scripts/ebid_search_contract.py --keyword "터널" --type 용역 --md
    python <스킬폴더>/scripts/ebid_search_contract.py --keyword "VMS" --detail --md   # 건별 상세까지

- 기간 미지정 시 최근 1년(체결일 기준).
- --detail: 건마다 상세 API 를 1회 더 호출해 계약기간·발주처·담당자/연락처·낙찰업체 대표/주소/지분·
  수의근거·설계금액/예정가격/개찰일시를 `상세` 키에 붙인다. 기본 상한 30건(--detail-limit).
- 계약은 건별 웹 딥링크가 없다. 조회 화면 진입: https://ebid.ex.co.kr/default.do?menuId=NPRO20001
  필드 의미·검증 근거는 references/ebid-필드사전.md §계약공개현황.
Exit: 0 성공 / 1 통신·응답 실패 / 2 인자·날짜 오류
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 어느 작업 폴더에서도 _ebid 를 찾는다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import argparse
import json
import time
from typing import Any

import requests

from _ebid.client import EbidClient
from _ebid.contracts import (CONTRACT_PAGE_URL, DEFAULT_DETAIL_LIMIT, MAX_RETRIES,
                             fetch_contract_detail, search_contracts)
from _ebid.normalize import (normalize_contract, normalize_contract_detail, print_table,
                             render_contract_markdown)
from _ebid.search import NOTICE_CLASS_LABELS, REQUEST_INTERVAL_SECONDS, resolve_date_window

SEARCH_LOOKBACK_DAYS = 365  # 대화형 검색 기본 폭 — 최근 1년


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ebid 계약공개현황 검색(수의·지명 포함 체결 원장). 입찰공고는 ebid_search_common.py")
    parser.add_argument("--keyword", required=True, help="계약명에 포함될 검색어")
    parser.add_argument("--from", dest="date_from", help="체결일 시작 YYYYMMDD (생략 시 최근 1년)")
    parser.add_argument("--to", dest="date_to", help="체결일 종료 YYYYMMDD (생략 시 오늘)")
    parser.add_argument("--type", dest="types", nargs="+", choices=["공사", "용역", "물품"],
                        help="발주유형 필터 (생략 시 전체 — 휴게소·단가 등 다른 유형도 포함)")
    parser.add_argument("--detail", action="store_true",
                        help="건별 상세 조회(계약기간·발주처·담당자·업체 대표/지분·수의근거·설계/예정가격)를 `상세` 키에 추가")
    parser.add_argument("--detail-limit", type=int, default=DEFAULT_DETAIL_LIMIT,
                        help=f"--detail 로 상세를 붙일 최대 건수 (기본 {DEFAULT_DETAIL_LIMIT}, 체결일 최신순)")
    parser.add_argument("--table", action="store_true", help="JSON 대신 사람용 표로 출력")
    parser.add_argument("--md", action="store_true",
                        help="JSON 대신 대화창용 마크다운 표로 출력 (--detail 이면 상세 열 추가)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        from_date, to_date = resolve_date_window(
            args.date_from, args.date_to, lookback_days=SEARCH_LOOKBACK_DAYS)
    except ValueError as exc:
        print(f"[ebid] 날짜 형식 오류: {exc}", file=sys.stderr)
        return 2
    if from_date > to_date:
        print(f"[ebid] --from({from_date})이 --to({to_date})보다 이후입니다.", file=sys.stderr)
        return 2
    if args.detail_limit < 0:
        print("[ebid] --detail-limit 은 0 이상이어야 합니다.", file=sys.stderr)
        return 2
    if not args.date_from:
        print(f"[ebid] 기간 미지정 → 기본 최근 1년({from_date}~{to_date}, 체결일 기준) 적용. "
              f"답변에 이 범위를 안내할 것 — 이력·과거 사업 질의면 --from 으로 범위를 넓혀 재검색",
              file=sys.stderr)

    client = EbidClient(max_retries=MAX_RETRIES)
    classes = [NOTICE_CLASS_LABELS[t] for t in args.types] if args.types else [None]
    raw: list[dict[str, Any]] = []
    try:
        for i, cls in enumerate(classes):
            if i > 0:
                time.sleep(REQUEST_INTERVAL_SECONDS)
            raw.extend(search_contracts(client, keyword=args.keyword, from_date=from_date,
                                        to_date=to_date, notice_class=cls))
    except requests.exceptions.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else "?"
        print(f"[ebid] 검색 실패: HTTP {status}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ebid] 검색 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    raw.sort(key=lambda it: str(it.get("cntg_date") or ""), reverse=True)
    rows = [normalize_contract(it) for it in raw]

    detail_failed = 0
    if args.detail:
        targets = list(zip(raw, rows))[:args.detail_limit]
        if len(rows) > args.detail_limit:
            print(f"[ebid] --detail 상한 {args.detail_limit}건 적용 — 전체 {len(rows)}건 중 체결일 최신순 "
                  f"{args.detail_limit}건만 상세 조회. 더 필요하면 --detail-limit 을 올리거나 기간을 좁힐 것",
                  file=sys.stderr)
        for i, (item, row) in enumerate(targets):
            if i > 0:
                time.sleep(REQUEST_INTERVAL_SECONDS)
            try:
                row["상세"] = normalize_contract_detail(fetch_contract_detail(client, item))
            except Exception as exc:  # 한 건 실패가 전체를 막지 않는다
                detail_failed += 1
                row["상세"] = None
                print(f"[ebid] 상세 실패 ({row.get('계약번호')}): {type(exc).__name__}: {exc}", file=sys.stderr)

    if args.md:
        period = "1년" if not args.date_from and not args.date_to else f"{from_date[:4]}-{from_date[4:6]}-{from_date[6:]}~{to_date[:4]}-{to_date[4:6]}-{to_date[6:]}"
        print(render_contract_markdown(rows, keyword=args.keyword, period_label=period,
                                       detail=args.detail), end="")
    elif args.table:
        print_table(rows)
    else:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"[ebid] keyword={args.keyword!r} types={args.types or '전체'} range={from_date}~{to_date} "
          f"count={len(rows)} detail={'on' if args.detail else 'off'}"
          f"{f' detail_failed={detail_failed}' if detail_failed else ''} page={CONTRACT_PAGE_URL}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
