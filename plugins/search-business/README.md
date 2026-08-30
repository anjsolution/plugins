# search-business

공공 발주 공고를 **찾고 → 어떻게 됐는지 보고 → 첨부를 받아 읽는** 플러그인입니다.
v0.1 은 한국도로공사 전자조달(ebid.ex.co.kr)을 지원합니다. 인증 없이 동작합니다.

## 설치

```
/plugin install search-business@anjsolution        # Claude Code
codex plugin add search-business@anjsolution        # Codex
```

Python 3.10+ 와 `pip install -r requirements.txt` (requests) 가 필요합니다.
hwp/hwpx/pdf 첨부를 읽으려면 문서 스킬(kordoc 등)을 함께 설치하세요.

## 할 수 있는 것

| 질문 | 도구 |
|---|---|
| "VMS 1년치 공고 검색해줘" | `ebid_search.py --keyword VMS` |
| "수의계약으로 체결된 것도" | `ebid_search.py --keyword 터널 --type 계약` |
| "202602664 누가 낙찰됐어?" | `ebid_result.py --notice 202602664` |
| "첨부 목록 보여줘 / 단가산출서만 받아줘" | `ebid_fetch.py --notice … --list` / `--only 단가 --out <폴더>` |

설치 후에는 평소처럼 질문하면 `ebid` 스킬이 알아서 도구를 씁니다.

## 구조

```
skills/ebid/
├── SKILL.md                 규칙 (검색·응답·첨부 판독)
├── scripts/                 공개 CLI 3개 + _ebid/ 내부 패키지 (codes.json 에 코드 매핑)
└── references/              필드 사전 · 문서 판독 지침 · 소스 접근성
```

## 소스 한계

자동 검색은 ebid 만. 나라장터·EIASS·관보는 `skills/ebid/references/소스-접근성.md` 참고.

## 검증

`tests/` 에 오프라인 테스트(`python -m pytest tests/`). 온라인 스모크는 공고 202506507(검색) /
202602664(개찰) / 202602663(첨부) 로 확인합니다.

## 문의

Ai-Ops · khchoi@anjsol.co.kr
