"""ebid 공고 첨부 목록 조회·다운로드 CLI (공고 여러 건 배치 처리).

    python <스킬폴더>/scripts/ebid_fetch.py --notice 202602663 --list
    python <스킬폴더>/scripts/ebid_fetch.py --notice 202602663
    python <스킬폴더>/scripts/ebid_fetch.py --notice 202605940 202605691 --out-dir ./자료
    python <스킬폴더>/scripts/ebid_fetch.py --notice 202602663 --only 단가산출서

--list 는 파일을 만들지 않는다. 다운로드는 `--out-dir` 밑에 공고별 `(공고번호)공고명/` 폴더를
만들어 받는다(기본 ./ebid-out). 검색 CLI 의 `--out` 은 파일 경로이지만 여기는 폴더라서 이름을
`--out-dir` 로 구분했다 — 같은 이름이면 파일 경로를 넘겨도 그 이름의 폴더가 조용히 생긴다.

공고를 여러 건 주면 세션을 한 번만 열고 공고 확인·목록·다운로드를 병렬로 돌린다
(실측: 10공고 40파일 211MB 가 직렬 177초 → 배치 28초).

실패한 첨부는 결과 JSON `실패` 에 공고번호·파일명·종류(network/http/server/file)·메시지로 남는다.
부분 실패(종료코드 3) 뒤에는 같은 명령에 `--skip-existing` 만 붙여 다시 돌리면 실패분만 받는다.
받은 목록은
받은 목록은 `<out-dir>/_받은목록.md` 에도 기록된다 — 파일이 공고별 폴더로 흩어지기 때문이다.
Exit: 0 성공 / 1 통신·조회 실패 / 2 공고 미발견 또는 인자 오류 / 3 부분 성공
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
from typing import Any

from _ebid.attachments import (MAX_DOWNLOAD_WORKERS, MAX_RETRIES, default_folder_name,
                               download_one_attachment, existing_download,
                               fetch_attachment_list, pick_workers, resolve_notice)
from _ebid.client import EbidClient
from _ebid.errors import NOTICE_NO_HINT, KoreanArgumentParser, is_notice_no, report_error
from _ebid.normalize import md_file_link
from _ebid.parallel import map_parallel

DEFAULT_OUT_DIR = "./ebid-out"
MANIFEST_NAME = "_받은목록.md"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = KoreanArgumentParser(description="ebid 공고 첨부파일 목록 조회·다운로드")
    parser.add_argument("--notice", nargs="+", required=True, metavar="공고번호",
                        help="공고번호 9자리. 여러 개를 띄어쓰기로 주면 배치 처리 (예: 202602663 202605940)")
    parser.add_argument("--out-dir", dest="out_dir", default=DEFAULT_OUT_DIR,
                        help=f"받을 위치 (기본 {DEFAULT_OUT_DIR}). 그 밑에 공고별 (공고번호)공고명 폴더가 생긴다")
    parser.add_argument("--list", dest="list_only", action="store_true",
                        help="다운로드 없이 첨부 목록만 출력 (파일을 만들지 않음)")
    parser.add_argument("--only", nargs="+", default=None,
                        help="파일명 부분일치 필터 — 일치하는 첨부만 다운로드")
    parser.add_argument("--skip-existing", dest="skip_existing", action="store_true",
                        help="이미 받은 파일(같은 폴더·이름·크기)은 건너뛴다 — 부분 실패 뒤 실패분만 재시도할 때")
    return parser.parse_args(argv)


def write_manifest(out_dir: Path, notices: list[dict[str, Any]]) -> Path:
    """받은 파일이 공고별 폴더로 흩어지므로 출처·크기·실패를 한 파일에 모아 둔다."""
    lines = ["# ebid 첨부 받은 목록", "",
             "받은 위치: " + md_file_link(out_dir.name or out_dir, out_dir.resolve()), ""]
    for n in notices:
        lines.append(f"## ({n['공고번호']}) {n['공고명']}")
        lines.append("- 폴더: " + md_file_link(Path(n["저장폴더"]).name, n["저장폴더"]))
        for f in n["저장"]:
            lines.append(f"  - {f['filename']} — {int(f.get('size') or 0):,}B")
        for f in n.get("건너뜀", []):
            lines.append(f"  - (건너뜀) {f['filename']} — {int(f.get('size') or 0):,}B ({f.get('사유')})")
        for f in n["실패"]:
            lines.append(f"  - (실패) {f['filename']} — [{f.get('종류')}] {f.get('error')}")
        lines.append("")
    path = out_dir / MANIFEST_NAME
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bad = [n for n in args.notice if not is_notice_no(n)]
    if bad:
        print(f"[ebid] 인자 오류: {NOTICE_NO_HINT} (입력: {', '.join(map(repr, bad))})", file=sys.stderr)
        return 2

    client = EbidClient(max_retries=MAX_RETRIES)
    try:
        client.ensure_csrf_token()  # 세션·토큰은 스레드 시작 전에 확보 (없으면 403)
    except Exception as exc:
        report_error("세션 준비 실패", exc)
        return 1

    def probe(notice_no: str) -> tuple[dict[str, Any] | None, list[dict], str]:
        notice = resolve_notice(client, notice_no)
        if notice is None:
            return None, [], ""
        attachments, source = fetch_attachment_list(client, notice)
        return notice, attachments, source

    probes = map_parallel(probe, args.notice, max_workers=MAX_DOWNLOAD_WORKERS)

    found: list[tuple[dict[str, Any], list[dict]]] = []
    missing: list[str] = []
    for notice_no, (result, exc) in zip(args.notice, probes):
        if exc is not None:
            report_error(f"공고 {notice_no} 조회 실패", exc)
            missing.append(notice_no)
            continue
        notice, attachments, source = result
        if notice is None:
            print(f"[ebid] 공고번호 {notice_no!r} 를 찾지 못했습니다 — 기간 제한 없이 조회했으니 "
                  f"공고번호가 정확한지 확인하세요.", file=sys.stderr)
            missing.append(notice_no)
            continue
        if args.only:
            attachments = [a for a in attachments
                           if any(pat in str(a.get("orgn_file_nm", "")) for pat in args.only)]
        print(f"[ebid] {notice_no} [{notice['noti_cls']}] {notice.get('noti_nm')!r} "
              f"상태={notice.get('prog_sts')} 첨부 {len(attachments)}건 (source={source})", file=sys.stderr)
        found.append((notice, attachments))

    if not found:
        return 2

    if args.list_only:
        print(json.dumps([{"공고번호": n["noti_no"], "공고명": n.get("noti_nm"),
                           "첨부": [{"파일명": a.get("orgn_file_nm"), "크기": a.get("att_file_siz")}
                                  for a in atts]}
                          for n, atts in found], ensure_ascii=False, indent=2))
        return 0 if not missing else 3

    out_dir = Path(args.out_dir)
    folders = {n["noti_no"]: out_dir / default_folder_name(n["noti_no"], n.get("noti_nm", ""))
               for n, _ in found}
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    skipped: list[tuple[str, dict[str, Any]]] = []
    for notice, atts in found:
        for attachment in atts:
            done = existing_download(attachment, folders[notice["noti_no"]]) if args.skip_existing else None
            if done is None:
                jobs.append((notice, attachment))
            else:
                skipped.append((notice["noti_no"], done))
    if skipped:
        print(f"[ebid] 이미 받은 {len(skipped)}개 건너뜀 (--skip-existing)", file=sys.stderr)
    if not jobs:
        print(f"[ebid] 받을 파일이 없습니다 (건너뜀 {len(skipped)}개).", file=sys.stderr)
        print("[]")
        return 0 if not missing else 3

    total_bytes = sum(int(a.get("att_file_siz") or 0) for _, a in jobs)
    workers = pick_workers([a.get("att_file_siz") for _, a in jobs])
    print(f"[ebid] {len(found)}개 공고 / {len(jobs)}개 파일 / {total_bytes / 1048576:.1f}MB "
          f"→ {out_dir} (동시 {workers})", file=sys.stderr)

    results = map_parallel(
        lambda job: download_one_attachment(client, attachment=job[1],
                                            notice_class=job[0]["noti_cls"],
                                            out_dir=folders[job[0]["noti_no"]]),
        jobs, max_workers=workers)

    per_notice: dict[str, dict[str, Any]] = {
        n["noti_no"]: {"공고번호": n["noti_no"], "공고명": n.get("noti_nm"),
                       "저장폴더": str(folders[n["noti_no"]].resolve()), "저장": [], "건너뜀": [], "실패": []}
        for n, _ in found}
    for (notice, attachment), (result, exc) in zip(jobs, results):
        entry = per_notice[notice["noti_no"]]
        if exc is not None:  # map_parallel 이 잡은 예외 — download_one_attachment 밖에서 터진 것
            entry["실패"].append({"filename": attachment.get("orgn_file_nm"),
                                 "종류": "unknown", "error": str(exc)})
        elif result.get("error"):
            entry["실패"].append(result)
        else:
            entry["저장"].append(result)

    for notice_no, done in skipped:
        per_notice[notice_no]["건너뜀"].append(done)

    notices = list(per_notice.values())
    manifest = write_manifest(out_dir, notices)
    saved = sum(len(n["저장"]) for n in notices)
    failed = sum(len(n["실패"]) for n in notices)
    # 경로는 절대경로로 낸다 — 호출자가 이 값으로 링크를 만들기 때문에 상대경로면 링크가 깨진다.
    print(json.dumps({"받은위치": str(out_dir.resolve()), "받은목록": str(manifest.resolve()),
                      "공고": notices, "미발견": missing,
                      "합계": {"공고": len(notices), "성공": saved,
                             "건너뜀": len(skipped), "실패": failed}},
                     ensure_ascii=False, indent=2))
    print(f"[ebid] 완료: {saved}/{saved + failed} 파일 성공, 받은목록 {manifest}", file=sys.stderr)
    for n in notices:
        for f in n["실패"]:
            print(f"[ebid] 실패: {n['공고번호']} {f['filename']} [{f.get('종류')}]", file=sys.stderr)

    if failed and not saved:
        return 1
    if failed or missing:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
