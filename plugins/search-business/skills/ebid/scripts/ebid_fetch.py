"""ebid 공고 첨부 목록 조회·다운로드 CLI.

    python <스킬폴더>/scripts/ebid_fetch.py --notice 202602663 --list
    python <스킬폴더>/scripts/ebid_fetch.py --notice 202602663 --out "./(202602663)공고명"
    python <스킬폴더>/scripts/ebid_fetch.py --notice 202602663 --only 단가산출서 --out ./tmp

--list 는 파일을 만들지 않는다. 다운로드는 --out 이 필수다(저장 위치를 호출자가 정한다).
실패한 첨부는 결과 JSON `실패` 에 파일명·종류(network/http/server/file)·메시지로 남는다.
Exit: 0 성공 / 1 통신·조회 실패 / 2 공고 미발견 또는 인자 오류 / 3 부분 성공
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 어느 작업 폴더에서도 _ebid 를 찾는다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json
import time
from typing import Any

from _ebid.attachments import (MAX_RETRIES, REQUEST_INTERVAL_SECONDS, download_one_attachment,
                               fetch_attachment_list, resolve_notice)
from _ebid.client import EbidClient
from _ebid.errors import NOTICE_NO_HINT, KoreanArgumentParser, is_notice_no, report_error

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = KoreanArgumentParser(description="ebid 공고 첨부파일 목록 조회·다운로드")
    parser.add_argument("--notice", required=True, help="공고번호 (예: 202602663)")
    parser.add_argument("--out", help="저장 폴더 (다운로드 시 필수)")
    parser.add_argument("--list", dest="list_only", action="store_true",
                        help="다운로드 없이 첨부 목록만 출력")
    parser.add_argument("--only", nargs="+", default=None,
                        help="파일명 부분일치 필터 — 일치하는 첨부만 다운로드")
    return parser.parse_args(argv)



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.list_only and not args.out:
        print("[ebid] 다운로드에는 --out <폴더> 가 필요합니다. 목록만 보려면 --list.", file=sys.stderr)
        return 2
    if not is_notice_no(args.notice):
        print(f"[ebid] 인자 오류: {NOTICE_NO_HINT} (입력: {args.notice!r})", file=sys.stderr)
        return 2
    client = EbidClient(max_retries=MAX_RETRIES)

    try:
        notice = resolve_notice(client, args.notice)
    except Exception as exc:
        report_error("공고 조회 실패", exc)
        return 1
    if notice is None:
        print(f"[ebid] 공고번호 {args.notice!r} 를 찾지 못했습니다 — 기간 제한 없이 "
              f"조회했으니 공고번호가 정확한지 확인하세요.", file=sys.stderr)
        return 2

    print(f"[ebid] 공고 확인: {notice['noti_no']} [{notice['noti_cls']}] "
          f"{notice.get('noti_nm')!r} 상태={notice.get('prog_sts')}", file=sys.stderr)

    time.sleep(REQUEST_INTERVAL_SECONDS)
    try:
        attachments, source = fetch_attachment_list(client, notice)
    except Exception as exc:
        report_error("첨부 목록 조회 실패", exc)
        return 1
    print(f"[ebid] 첨부 {len(attachments)}건 (source={source})", file=sys.stderr)

    if args.only:
        attachments = [a for a in attachments
                       if any(pat in str(a.get("orgn_file_nm", "")) for pat in args.only)]
        print(f"[ebid] --only 필터 후 {len(attachments)}건", file=sys.stderr)

    if args.list_only:
        listing = [{"파일명": a.get("orgn_file_nm"), "크기": a.get("att_file_siz")}
                   for a in attachments]
        print(json.dumps({"공고번호": notice["noti_no"], "공고명": notice.get("noti_nm"),
                          "첨부": listing}, ensure_ascii=False, indent=2))
        return 0

    if not attachments:
        print("[]")
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[ebid] 저장 폴더: {out_dir}", file=sys.stderr)

    results: list[dict[str, Any]] = []
    for index, attachment in enumerate(attachments):
        if index > 0:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        result = download_one_attachment(
            client, attachment=attachment, notice_class=notice["noti_cls"], out_dir=out_dir)
        note = (f"실패[{result.get('종류')}] {result['error']}" if result.get("error")
                else f"{result.get('size')}B")
        print(f"[ebid]   - {result['filename']}: {note}", file=sys.stderr)
        results.append(result)

    saved = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    print(json.dumps({"공고번호": notice["noti_no"], "공고명": notice.get("noti_nm"),
                      "저장폴더": str(out_dir), "저장": saved, "실패": failed},
                     ensure_ascii=False, indent=2))
    print(f"[ebid] 완료: {len(saved)}/{len(results)} 성공", file=sys.stderr)
    if failed:
        print("[ebid] 실패: " + ", ".join(f"{r['filename']}[{r.get('종류')}]" for r in failed), file=sys.stderr)
    if not failed:
        return 0
    if not saved:
        return 1
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
