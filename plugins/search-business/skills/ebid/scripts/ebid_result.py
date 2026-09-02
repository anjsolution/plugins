"""ebid 공고 상세·입찰결과 — 공고번호 하나로 "이 공고 어떻게 됐어?"에 답한다.

공고 기본정보(상태·계약방법·설계금액·개찰일시)와 개찰 결과(낙찰업체·낙찰금액·
낙찰률·참가업체 목록·재공고 연결)를 함께 출력한다. 아직 개찰 전이면 결과 없이
공고 정보와 "입찰 진행 중"만 출력된다. 같은 번호에 차수가 여럿이면 최신 차수.

    python <스킬폴더>/scripts/ebid_result.py --notice 202602664
    python <스킬폴더>/scripts/ebid_result.py --notice 202602664 --table

Exit: 0 성공 / 1 통신 실패 / 2 공고 미발견·인자 오류
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

from _ebid.attachments import (MAX_RETRIES, REQUEST_INTERVAL_SECONDS, fetch_attachment_list,
                               resolve_notice)
from _ebid.client import EbidClient
from _ebid.errors import NOTICE_NO_HINT, KoreanArgumentParser, is_notice_no, report_error
from _ebid.normalize import fmt_dt, normalize_notice

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = KoreanArgumentParser(description="ebid 공고 상세·입찰결과 조회")
    parser.add_argument("--notice", required=True, help="공고번호 (예: 202602664)")
    parser.add_argument("--table", action="store_true", help="JSON 대신 사람용 요약으로 출력")
    return parser.parse_args(argv)


def to_int(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def build_result(detail: dict[str, Any]) -> dict[str, Any]:
    vendors = detail.get("findListResultVd") or []
    estm = detail.get("estmInfo") or {}
    amt = detail.get("amtData") or {}
    participants = []
    winner: dict[str, Any] | None = None
    for v in vendors:
        row = {
            "업체명": v.get("vd_nm"),
            "사업자번호": v.get("vd_cd"),
            "투찰금액원": to_int(v.get("dec_amt")),
            "비고": v.get("rem") or "",
        }
        participants.append(row)
        if str(v.get("rem") or "") == "낙찰":
            winner = row
    dsgng = to_int(estm.get("dsgng_amt"))
    result: dict[str, Any] = {
        "참가업체수": len(participants),
        "참가업체": participants,
        "설계금액원": dsgng,
        "예정가격원": to_int(estm.get("last_estct_amt")),
    }
    if winner:
        result["낙찰업체"] = winner["업체명"]
        result["낙찰금액원"] = winner["투찰금액원"]
        # amtData.BamtToDamt = 낙찰금액/예정가격 비율(%) 실측 — 없으면 설계금액 대비 계산
        rate = amt.get("BamtToDamt")
        if rate:
            result["낙찰률_퍼센트"] = rate
        elif winner["투찰금액원"] and dsgng:
            result["낙찰률_퍼센트"] = round(winner["투찰금액원"] / dsgng * 100, 2)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
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

    summary = normalize_notice(notice)

    time.sleep(REQUEST_INTERVAL_SECONDS)
    try:
        detail = client.find_info_result_detail(
            noti_id=notice["noti_id"], noti_cont_id=notice["noti_cont_id"],
            noti_no=notice["noti_no"], bid_no=notice["bid_no"],
            bid_rev=notice["bid_rev"], notice_class=notice["noti_cls"],
        )
    except Exception as exc:
        report_error("입찰결과 조회 실패", exc)
        return 1

    # 첨부 목록도 같은 명령에서 받는다 — 공고 한 건을 볼 때 "무슨 문서가 붙어 있나" 는 거의 항상
    # 따라오는 질문이라, 사용자가 명령을 두 번 치게 할 이유가 없다. 실패해도 나머지는 낸다.
    time.sleep(REQUEST_INTERVAL_SECONDS)
    try:
        attachments, _src = fetch_attachment_list(client, notice)
    except Exception as exc:
        report_error("첨부 목록 조회 실패(나머지는 출력)", exc)
        attachments = []

    detail_data = detail.get("detailData") or {}
    output: dict[str, Any] = {
        "공고": summary,
        "첨부": [{"파일명": a.get("orgn_file_nm"), "크기": a.get("att_file_siz")} for a in attachments],
        "개찰결과": build_result(detail),
    }
    if detail_data.get("prev_noti_no"):
        output["재공고_원공고번호"] = detail_data["prev_noti_no"]
    if detail_data.get("stl_cancel_dt"):
        output["취소일시"] = fmt_dt(detail_data["stl_cancel_dt"])

    if args.table:
        s = summary
        print(f"[{s['발주유형']}] {s['공고번호']} {s['공고명']}")
        # 제한유형(HC)·업종(3000) 은 매핑이 없어 코드 그대로일 수밖에 없다. 사람이 못 읽는 값을
        # 화면에 두면 소음이라 표에서 뺀다 — JSON 에는 그대로 남으니 필요하면 거기서 본다.
        print(f"  {s['지역']} | 공고일 {s['공고일']} | 상태 {s['상태']} | {s['계약방법']} | 차수 {s.get('차수', '-')}")
        print(f"  입찰마감 {s.get('입찰마감일시') or '-'} | 개찰 {s['개찰일시'] or '-'} | PQ {s.get('PQ여부') or '-'}")
        r = output["개찰결과"]
        dsg = f"{r['설계금액원']:,}" if r.get("설계금액원") else "-"
        print(f"  설계금액 {dsg}원 | 참가 {r['참가업체수']}개사")
        att = output["첨부"]
        if att:
            total = sum(int(a.get("크기") or 0) for a in att)
            print(f"  첨부 {len(att)}개 ({total / 1048576:.1f}MB)")
            for a in att:
                size = int(a.get("크기") or 0)
                unit = f"{size / 1048576:.1f}MB" if size >= 1048576 else f"{size / 1024:.0f}KB"
                print(f"    - {a['파일명']} ({unit})")
        else:
            print("  첨부 없음")
        if r.get("낙찰업체"):
            print(f"  낙찰: {r['낙찰업체']} | {r['낙찰금액원']:,}원"
                  f" | 낙찰률 {r.get('낙찰률_퍼센트', '-')}%")
        else:
            # 상태 라벨과 파생 필드 「입찰단계」로 충분하다. 상태별 설명을 따로 두면
            # 대부분 동어반복이 되고, 상태 의미가 codes.json·입찰단계에 이어 세 번째로 흩어진다.
            print(f"  낙찰자 없음 — 상태 {s['상태']} / {s.get('입찰단계', '')}")
        for p in r["참가업체"]:
            amt = f"{p['투찰금액원']:,}" if p.get("투찰금액원") else "-"
            print(f"    - {p['업체명']} | {amt}원 | {p['비고']}")
        if output.get("재공고_원공고번호"):
            print(f"  재공고 — 원공고: {output['재공고_원공고번호']}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
