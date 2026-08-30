"""ebid 입찰공고 검색 — 공사·용역·물품 공고를 키워드로 찾는다.

계약공개현황(수의·지명 포함 체결 원장)은 별도 도구 ebid_search_contract.py.
결과는 한글 키로 정규화한 JSON 배열(stdout). --md 는 대화창용 표, --table 은 한 줄 표. 진단은 stderr.

    python <스킬폴더>/scripts/ebid_search_common.py --keyword "구내통신" --from 20260101
    python <스킬폴더>/scripts/ebid_search_common.py --keyword "VMS" --type 공사 물품 --table
    python <스킬폴더>/scripts/ebid_search_common.py --keyword "ITS" --md   # 대화창용
    python <스킬폴더>/scripts/ebid_search_common.py --from 20260815 --type 용역 --md   # 키워드 없이 최근 공고 전체

- 기간 미지정 시 최근 1년. 공고번호 조회에는 기간 개념이 없다(ebid_result / ebid_fetch).
- --keyword 생략 시 검색어 없이 기간 내 전체를 가져온다(요청 본문에서 noti_nm 제외). 이때 --from 은 필수
  (없으면 종료코드 2). 건수 제한은 두지 않으므로 호출 측이 기간을 좁혀야 한다(SKILL.md 검색 규칙).
- 출력은 "아는 필드는 한글 키로 정규화 + 나머지 원본 필드 passthrough".
  필드 의미·상태코드·딥링크 규칙은 references/ebid-필드사전.md.
Exit: 0 성공 / 1 통신·응답 실패 / 2 인자·날짜 오류
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 어느 작업 폴더에서도 _ebid 를 찾는다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json
from typing import Any

from _ebid.client import EbidClient
from _ebid.errors import DATE_HINT, KoreanArgumentParser, report_error
from _ebid.normalize import (normalize_notice, print_table, render_notice_html,
                             render_notice_markdown, write_output)
from _ebid.parallel import map_parallel
from _ebid.search import NOTICE_CLASS_LABELS, STATUS_FILTER_OVERRIDE, resolve_date_window

MAX_RETRIES = 2
SEARCH_LOOKBACK_DAYS = 365  # 대화형 검색 기본 폭 — 최근 1년

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = KoreanArgumentParser(description="ebid 입찰공고 검색(공사·용역·물품). 계약공개현황은 ebid_search_contract.py")
    parser.add_argument("--keyword", default="", help="공고명에 포함될 검색어 (생략 시 기간 내 전체 — 이때 --from 필수)")
    parser.add_argument("--from", dest="date_from", help="시작일 YYYYMMDD (생략 시 최근 1년)")
    parser.add_argument("--to", dest="date_to", help="종료일 YYYYMMDD (생략 시 오늘)")
    parser.add_argument(
        "--type", dest="types", nargs="+", default=["공사", "용역", "물품"],
        choices=["공사", "용역", "물품"],
        help="발주유형 (기본: 공사 용역 물품 전부)",
    )
    parser.add_argument("--table", action="store_true", help="JSON 대신 사람용 표로 출력")
    parser.add_argument("--html", action="store_true", help="JSON 대신 HTML 표(브라우저·Artifact 용, 공고명 링크)")
    parser.add_argument("--out", help="결과를 이 파일에 저장하고 stdout 에는 내지 않음 (형식은 --md/--html/JSON 그대로)")
    parser.add_argument("--md", action="store_true",
                        help="JSON 대신 대화창용 마크다운 표로 출력 (발주유형별 표 + 공고명 딥링크)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.keyword and not args.date_from:
        print("[ebid] --keyword 없이 검색하려면 --from 이 필수입니다 (기간 내 전체를 가져오므로). "
              "예: --from 20260815 [--to 20260830] [--type 용역]", file=sys.stderr)
        return 2
    try:
        from_date, to_date = resolve_date_window(
            args.date_from, args.date_to, lookback_days=SEARCH_LOOKBACK_DAYS)
    except ValueError as exc:
        print(f"[ebid] 날짜 형식 오류 — {DATE_HINT} (입력: {str(exc).split(': ', 1)[-1]})", file=sys.stderr)
        return 2
    if from_date > to_date:
        print(f"[ebid] --from({from_date})이 --to({to_date})보다 이후입니다.", file=sys.stderr)
        return 2
    if not args.date_from:
        print(f"[ebid] 기간 미지정 → 기본 최근 1년({from_date}~{to_date}) 적용. "
              f"답변에 이 범위를 안내할 것 — 이력·과거 사업 질의면 --from 으로 범위를 넓혀 재검색",
              file=sys.stderr)

    if not args.keyword:
        print(f"[ebid] 키워드 없음 → {from_date}~{to_date} 기간 내 전체 공고. 건수가 많으면 기간을 더 좁힐 것",
              file=sys.stderr)
    overrides: dict[str, Any] = {"arr_status": STATUS_FILTER_OVERRIDE}
    if args.keyword:
        overrides["noti_nm"] = args.keyword
    client = EbidClient(max_retries=MAX_RETRIES)
    rows: list[dict[str, Any]] = []
    try:
        client.ensure_csrf_token()  # 세션·토큰은 스레드 시작 전에 확보 (없으면 403)
    except Exception as exc:
        report_error("검색 실패", exc)
        return 1

    def fetch(label: str) -> list[dict[str, Any]]:
        items, _st, _url = client.fetch_bid_notice_list(
            notice_class=NOTICE_CLASS_LABELS[label], from_noti_date=from_date,
            to_noti_date=to_date, payload_overrides=overrides)
        return items

    for label, (items, exc) in zip(args.types, map_parallel(fetch, args.types)):  # 유형별 동시 조회
        if exc is not None:
            report_error(f"검색 실패({label})", exc)
            return 1
        rows.extend(normalize_notice(it) for it in items or [])

    rows.sort(key=lambda r: r.get("공고일") or "", reverse=True)
    period = "1년" if not args.date_from and not args.date_to else f"{from_date[:4]}-{from_date[4:6]}-{from_date[6:]}~{to_date[:4]}-{to_date[4:6]}-{to_date[6:]}"
    if args.md:
        write_output(render_notice_markdown(rows, keyword=args.keyword, period_label=period), args.out)
    elif args.html:
        write_output(render_notice_html(rows, keyword=args.keyword, period_label=period), args.out)
    elif args.table:
        print_table(rows)
    else:
        write_output(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", args.out)
    print(f"[ebid] keyword={args.keyword!r} types={args.types} "
          f"range={from_date}~{to_date} count={len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
