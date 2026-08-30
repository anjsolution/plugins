# ebid API 필드 사전

`ebid_search_common.py` / `ebid_search_contract.py` / `ebid_result.py` 가 다루는 원본 API 필드의 **의미·값 분포·검증 방법** 원장.
코드→한글 라벨 값 자체는 `scripts/_ebid/codes.json` 에 있다 — 이 문서는 그 매핑을 믿어도 되는 **근거**와,
새 코드·필드가 나타났을 때 **같은 방법으로 재검증**하기 위한 기록이다.

## 목차
- 검증 표본과 방법
- 출력 원칙 — passthrough 정규화
- 입찰공고 목록 API 필드표
- 상태코드(prog_sts) 해독
- 계약공개현황 API 필드표 / 계약 상세 API 필드표 / 계약 화면 구조·웹 진입
- 지역(area) 코드 확정 근거
- 딥링크 조립 규칙

## 검증 표본과 방법

- 입찰공고 184건: 공사 "vms" 21 + 용역 "터널" 149 + 물품 "vms" 14 (최근 1년)
- 계약공개현황 620건: "터널" (최근 1년)
- 지역 매핑 교차검증 645건: 공고명에 "본부" 포함, 2년치 3유형
- 방법: 원본 item 의 전체 키를 유형별로 합집합 수집 → 필드별 값 분포(`Counter`)
  → 공고명 정규식(`(수도권|서울경기|...)본부`) 추출값과 `area` 크로스탭

## 출력 원칙 — passthrough 정규화

`normalize_notice` / `normalize_contract` 는 **아는 필드만 한글 키로 정규화**하고,
소비되지 않은 나머지 원본 필드는 원본 키 그대로 출력에 덧붙인다(passthrough).
화이트리스트로 손수 나열하다 `area`(지역)를 통째로 버린 사고의 재발 방지 구조 —
API 에 새 필드가 생기면 자동으로 노출된다. 제외는 전 건 상수로 검증된 필드만
(`codes.json` 의 `제외필드`, 사유는 아래 필드표).

## 입찰공고 목록 API — 필드표

유형별 키는 동일(물품만 `rmcn_yn` 추가, 27~28개). ✔ = 한글 키로 정규화됨.

| 원본 키 | 정규화 | 의미 | 근거·값 분포(표본 184건) |
|---|---|---|---|
| `noti_no` | ✔ 공고번호 | 유일키 | |
| `noti_nm` | ✔ 공고명 | | |
| `noti_cls` | ✔ 발주유형 | CT=공사, SV=용역, MT=물품 (`codes.json` 발주유형) | |
| `area` | ✔ 지역(+지역코드) | 기관권역 코드 (`codes.json` 지역) | 아래 "지역 코드 확정 근거" |
| `noti_date` | ✔ 공고일 | YYYYMMDD | |
| `prog_sts` | ✔ 상태(+상태코드) | 2자리 상태 코드 (`codes.json` 상태정확·상태첫글자) | 아래 "상태코드 해독" |
| `cpt_terms` | ✔ 계약방법(+코드) | `codes.json` `계약방법` 정적 매핑(CTA 일반경쟁·CTE 지명경쟁·CTH 제한경쟁·CTL 전자수의 — 출처 공통코드 `PE080*`/`BID_USE_YN`). 종전 PE075* 실시간 조회는 `[{data:null,label:"전체"}]` 빈 응답이라 제거(2026-08-30) | 최근 1년 2,616건: CTH 1960 / CTA 656 |
| `lmtcpt_apply_bas_cd` | ✔ 제한유형코드 | HF 등 — 미해독 | |
| `bid_shpr1` | ✔ 업종 | 업종 제한. 용역=라벨(건설기술용역×107, 기타×32, 학술연구용역×6, 정보통신용역×4), 공사=코드("3000"×21), 물품=None | 업종 제한 선별에 유용 |
| `bid_shpr1_ct`, `bid_shpr1_sv` | (업종에 흡수) | `bid_shpr1` 과 전 건 동일값 — 중복 필드 | |
| `bid_shpr2` | passthrough | 부업종 코드 추정 — 공사에서만 "0036"×21, 미해독 | |
| `pq_yn` | ✔ PQ여부 | PQ(입찰참가자격 사전심사) 여부 | Y×116 / N×68 |
| `pq_type` | passthrough | PQ 유형 — A×106, N×68, S×10, 미해독 | |
| `dsgng_amt` | ✔ 설계금액원 | | |
| `bid_end_dt`, `open_dt` | ✔ 입찰마감/개찰일시 | YYYYMMDDHHMM | |
| `bid_rev` | ✔ 차수 | | |
| `noti_view_cnt` | passthrough | 공고 조회수 — 시장 관심도 참고 지표 | distinct 159 |
| `plrl_bid_cnt` | passthrough | 미해독 | 1×181, 2×2, 6×1 |
| `rmcn_yn` | passthrough | 물품에만 존재 — 레미콘 여부 추정(딥링크 물품 URL 의 remicon 파라미터로 전달) | None×170, N×14 |
| `detl_cont_end_dt` | passthrough | 표본 전 건 null | |
| `noti_id`, `noti_cont_id` | passthrough | 내부 UUID — **딥링크 조립 재료** (아래 §딥링크) | |
| (조립) | ✔ 딥링크 | default.do 공고 상세 진입 URL | 아래 §딥링크 |
| `sys_id`, `page`, `bid_no`, `fngprt_bid_yn` | **제외** | 전 건 상수: "NEBID", "noti", 1, "Y"(지문입찰) | `codes.json` 제외필드 |

## 상태코드(prog_sts) 해독

공고 308건(+사슬 후속 2건)의 검색행·입찰결과 상세를 교차해 해독했다.
방법: 공고번호별 원본 JSON 을 보존해 두고, 코드별로 **낙찰행 유무 × 참가업체 수 × 취소일시 ×
재공고 링크(prev_noti_no) × 후속 공고 존재**를 집계한다. 새 코드가 나타나면 같은 방법으로
검증해 이 표와 `codes.json` 을 갱신한다.

| 코드 | 건수 | 실측 근거 | 해석 (신뢰도) |
|---|---|---|---|
| UB | 246 | 246/246 낙찰행 존재 | **낙찰 성립** (확정적) |
| CB | 12+2 | 낙찰 0. PE074 공식 라벨 | **취소공고** (공식) |
| EY | 21 | 낙찰 0·참가 0. PE074 라벨 "공고중" | 마감 미도래=공고중 / **마감 경과분은 미개찰 종결(유찰)** — 상태가 갱신되지 않고 남음 |
| UA | 11 | 낙찰 0, 9건에 동일 공고명 후속 존재 | **유찰(낙찰 없이 종결)** (관측 일관) |
| AY | 8 | 단일 발주 배치(2017-12)에서만 — 참가 0, 전량 이듬해 재발주 | 무산·연기류 추정 (단일 배치 관측 — 일반화 금지) |
| MY | 5 | **참가업체 5개씩 있으나 낙찰행 없음** (대형 국제입찰 공사). 계약공개현황 역추적: 일반경쟁 공구는 본공사 계약이 공고번호로 잡히는데 MY 공구는 **"우선시공분" 계약(계약방법 "대안")**만 잡힘 | **대안·기술형 입찰로 낙찰이 이 화면에 미기재** (관측 일관 — "낙찰미표시"로 표기) |
| QQ | 4 | 정기안전점검 수행기관 지정공고류에서만 관측 | 지정공고 전용 상태 (낙찰 개념 없음) |
| UP / KY / OO | 각 1 | UP·KY 참가 0 / OO 참가 2·후속 존재 | 유찰류 추정 (n=1 — 규칙화 금지) |

부수 실측:

- **같은 공고번호에 차수(bid_rev)별 행이 여러 개** 올 수 있다 — 차수 1 취소(CB) 후 같은 번호로
  재입찰해 차수 2 낙찰(실측 201700462, 202503233). **`noti_cont_id` 는 차수마다 다르다**
  (`noti_id` 는 동일) — 첨부 그룹(fileAttList)도 차수 판을 따르므로 상세·첨부 조회는 최신 차수
  식별자로 해야 한다. `resolve_notice()` 가 최신 차수 행을 반환하는 이유(다중 차수 감지 시 stderr 경고).
- 입찰결과 상세 `detailData.prev_noti_no` = 재공고의 원공고번호(공식 사슬). 단 있는 건과 없는 건이
  섞여 있어 사슬 복원엔 동일 공고명·시간순 판정 병행 필요.
- `detailData.stl_cancel_dt` = 취소일시. 낙찰행과 공존 사례 1건(201701248 — 낙찰 후 계약 단계 취소 흔적, n=1).
- `detailData.sts`·`estmInfo.sts` 는 취소·낙찰 불문 전 건 "C" — 판별력 없음.
- PE074 공통코드는 화면 필터 정의(E/F/C/U/R 5묶음)일 뿐 전체 코드 열거가 아니다.
  `dtl_cd_attr_val` 로 묶음 구성(U=CB,UB,UP 등)만 확인 가능.

## 계약공개현황 API — 필드표 (16개)

| 원본 키 | 정규화 | 의미 | 근거·값 분포(표본 620건) |
|---|---|---|---|
| `cntr_nm` | ✔ 계약명 | | |
| `noti_cls` | ✔ 발주유형 | | |
| `cntg_date` | ✔ 체결일 | | |
| `g2b_snd_cpt_terms` | ✔ 계약방법 | 한글 라벨로 옴("전자수의" 등) | |
| `cntr_amt` | ✔ 계약금액원 | | |
| `com_nm` | ✔ 업체명 | | |
| `biz_no` | ✔ 사업자번호 | 동명 업체 구분·업체 추적 집계용 | distinct 390 |
| `stl_noti_no` | ✔ 계약번호(+연결공고번호) | **11자리 = 공고번호 9자리 + 접미 2자리.** 접미 앞자리 = 묶음 공고 안의 세부 건 순번(202603454 의 6건 묶음 감리용역이 `…31/41/51/61` 로 갈라짐), 뒷자리 = `1`(차수로 추정 — 재입찰 사례 미확인). 끝 2자리를 떼면 공고번호 | 표본 39건 전부 11자리, 접미 `11`×35 |
| `svsn_dept_nm` | ✔ **주관부서** | **실수요 부서** — "시설처 전기부"×137, "부산경남본부 교통부"×29 등 | distinct 105. 분석 시 계약부서 말고 이걸 쓸 것 |
| `cntr_dept_nm` | ✔ 계약부서 | 계약 행정 부서("○○본부 재무부" 류) | |
| `bid_cls` | passthrough | 입찰 구분 — **01=입찰공고 경유(일반·제한·지명경쟁), 03=견적(전자수의·희망수량)**. 2026-07~08 700건 크로스탭 모순 0건 | 01×311, 03×389 |
| `svsn_dept_cd`, `cntr_dept` | passthrough | 부서 코드(이름 필드의 코드짝) | |
| `cntr_id`, `org_cntr_id`, `noti_id` | passthrough | 내부 UUID | |

### 계약공개현황 검색 파라미터 (화면 `es-sp-cntr-open-list` 바인딩, 실측 2026-08-30)

| 파라미터 | 의미 | 실측 |
|---|---|---|
| `from_yyyymmdd`, `to_yyyymmdd` | 체결일 범위 | 필수. 7년 단일 호출 동작 |
| `cntr_nm` | 계약명 부분일치 | "터널" 3개월 193건 |
| `gubun` | 발주유형(CT/SV/MT …) — 공통코드 `PE000*`/`CT_USE_YN` | `CT` → 237건. **SX 휴게소·IF 단가·RB 감정평가도 계약공개 대상(Y)** |
| `method` | 계약방법 코드 — 공통코드 `PE080*`/`BID_USE_YN`: CTA 일반경쟁·CTE 지명경쟁·CTH 제한경쟁·CTL 전자수의 | `CTH` → 379건 |
| `stl_noti_no` | 계약번호(11자리) 정확일치 | 1건 |
| `oper_org_cd`, `stl_noti_nos` | 화면 바인딩만 확인, 미검증 | |

`ebid_search_contract.py` 는 `cntr_nm` + 기간 + (`--type` 시) `gubun` 을 보낸다.

### 계약 상세 API — 필드표 (`--detail`)

- **엔드포인트**: `POST /ui/sp/expro/cntropen/findInfoCntrOpnDetail.do`, menucode NPRO20001, 200 확인.
- **body 는 목록 행 전체** (화면 `es-sp-cntr-open-detail` 이 `detailData` = 클릭한 행을 그대로 보냄).
  **`{"cntr_id"}` 만 보내면 `bidInfo`·`cntrBasInfo` 가 null** 로 온다 — 2026-08-30 실측으로 이전 기록
  ("body `{cntr_id}`", "bidInfo null = 지명·전자수의 판별법")을 **정정**. 행 전체를 보내면 일반·제한·지명·
  전자수의 12/12 건 모두 채워지고, **`희망수량` 3/3 건만 `bidInfo` null**(`cntrBasInfo` 는 있음). 전자수의도
  전자 견적을 거치므로 설계금액·예정가격·개찰일시가 있다.
- 응답 6섹션. `normalize_contract_detail()` 이 한글 키 한 겹으로 편다.

| 섹션 | 원본 키 | 정규화 | 비고 |
|---|---|---|---|
| `cntrOpnDetail` | `cntr_sd`, `cntr_ed`, `cntr_day` | 계약기간(`sd~ed`), 계약일수 | 계약 종료일 → 재발주 시점 추정 |
| | `poor` | 발주처 | "전북본부", "보은지사" 등 |
| | `jhhm` + `claus_cd_etc_cause`, `claus_cd` | 수의근거(`조문 — 사유`), 수의근거코드 | 예: "026조 01항 05호 가목 — 추정가격 … 5천만원 이하", "혁신제품 구매". 경쟁입찰 건은 null |
| | `jhhmj/jhhmh/jhhmo/jhhmm` | passthrough 안 함 | `jhhm` 의 분해값(조/항/호/목) |
| `repVdInfo` (list) | `vd_nm`, `rep_nm`, `dtl_addr`, `phone_no`, `shar_rate` | 계약업체상세[{업체명, 대표자, 주소, 전화, 지분율}] | 공동도급이면 여러 행(60 %/40 % 실측). `vd_sn` 은 의미 미확정 |
| `deptAddr` | `chr_nm`, `chr_dept_phone_no1~3`, `chr_dept_addr`, `chr_dept_post_no1~2` | 담당자, 담당부서전화(`063-840-0208`), 담당부서주소, 담당부서우편번호 | 목록의 `svsn_dept_nm`(주관부서)와 별개인 **계약 담당자** |
| `bidInfo` (희망수량 제외) | `dsgng_amt`, `open_dt`, `cpt_terms_str`, `lmtcpt_apply_bas_cd_str`, `stl_terms_str`, `pq_type_str`, `bid_nm` | 설계금액원, 개찰일시, 경쟁방법, 제한기준("지역"), 낙찰방법("적격심사"/"중소기업 적격심사"/"기술용역 적격심사"), PQ | `unsc_dty_yn`, `plrl_prc_yn` 은 미소비 |
| `cntrBasInfo` | `expt_amt`, `noti_nm`, `noti_date` | 예정가격원, 공고명(`[긴급][국제입찰]` 접두 포함), 공고일 | 설계금액·예정가격·계약금액 3종으로 낙찰률 계산 가능 |
| `getSwYn` | `sw_yn` | SW계약여부 | Y 면 화면에 "SW사업 계약정보" 팝업 버튼 |

- **SW 팝업 API** `POST /ui/sp/expro/cntropen/getSwInfo.do` body `{cntr_id}`: `cntrData`(**계약번호 `cntr_no`** —
  목록엔 없음), 하도급 현황 `sbcnData`, 감리 `ctsvcnData`, 감독원 `svcnUserData`, 기성·준공검사 `accountList`,
  기성 지급 `payData`. SW 계약이 아니어도 200 + 빈 배열 + `cntrData` 는 온다. 플러그인은 아직 미사용.

### 계약 화면 구조·웹 진입 (소스 확인 2026-08-30)

- 쉘 `default.do?menuId=…` 는 `findListMenu.do` 의 메뉴 목록(GUEST 52개)에서 `menu_url` 을 찾아 컴포넌트를 띄우고
  `UT.parseUrlParam(location.href)` 를 `params` 로 넘긴다. 라우팅은 **메뉴 목록에 있는 ID 만**.
- 계약 메뉴: `NPRO20001 계약공개현황 조회 → cntropen/em-sp-cntr-open.html`, **`NPRO20002 변경계약현황 조회 →
  cntropen/em-sp-cntr-modify.html`**(미구현 진입점). 상세 컴포넌트를 직접 가리키는 메뉴는 없다.
- `em-sp-cntr-open`(컨테이너) → `es-sp-cntr-open-list`(목록: `load` 가 곧바로 `findListCntrOpn`) →
  `cntr_nm` 셀 클릭 `fire('show-detail', 행)` → `onShowDetail(e, data)` → `es-sp-cntr-open-detail.load(param, data)`.
  **세 컴포넌트 어디도 `this.params` 를 읽지 않는다** → 기간 프리필·건별 딥링크 불가 확정.
  (`es-sp-cntr-open-detail.html?bust=…` 요청은 딥링크가 아니라 컴포넌트 템플릿 HTML import.)
- **웹 진입**: `https://ebid.ex.co.kr/default.do?menuId=NPRO20001` 이 비로그인(GUEST)으로 조회 화면을 연다.
  건별 상세는 페이지를 연 뒤 콘솔/자동화에서
  `document.querySelector('em-sp-cntr-open').onShowDetail(null, {cntr_id: '<cntr_id>'})` 를 호출하면 렌더된다
  (헤드리스 Chrome 실검증 — 제목 "계약공개현황 상세"·담당자·계약기간 표시). 공유 가능한 URL 은 아니다.
- `bid_cls`=01 건은 입찰공고가 있으므로 공고 딥링크(§딥링크)로 대신 연결할 수 있다 — 상세 응답에는
  `noti_cont_id` 가 없으므로 `stl_noti_no[:-2]`(공고번호)로 공고 검색을 거쳐 조립한다. 03(전자수의·희망수량)은
  입찰공고 목록에 없어 딥링크 불가.

## 지역(area) 코드 확정 근거

값은 `codes.json` 의 `지역`(01~08, 0A, 0B).

- **출처**: 공식 코드표 미확보. 사이트 공통코드 API `findCommonCodeAttrCdList.do` 를 PE001~PE200 전수
  스윕했으나 area 그룹 없음. 화면 UI 는 자체 JS 매핑으로 추정.
- **검증 방법**: 공고명 "본부" 검색 2년치 645건에서 공고명 정규식 추출 본부명 × `area` 크로스탭 →
  03~0B 모순 0건 1:1.
- **예외 해명 (모순 아님)**:
  - `02`+"수도권본부" 9건 — 전부 2024-10~2025-03 공고. 2025년 상반기 조직개편으로 02 권역이
    수도권본부→**서울경기본부**로 개칭, 신설 `0B`가 현행 수도권본부. 과거 데이터는 시기에 따라 02 를
    "수도권본부(구)"로 읽을 것.
  - `01`+본부명 2건 — 전국 묶음 용역을 **본사가 통합 발주**한 사례. 공고명이 아니라 `area` 를 믿어야
    하는 이유의 실례.
- **주의**: 조직개편으로 코드 추가·명칭 변경 가능. 매핑에 없는 코드가 passthrough 로 나타나면 같은
  크로스탭 방법으로 재검증해 `codes.json` 을 갱신한다.

## 딥링크 — 공고 상세 웹 URL 조립

`_ebid/normalize.py build_notice_deeplink()` 가 구현체. 메뉴 ID·part 는 `codes.json` 의 `딥링크메뉴`.

```
https://ebid.ex.co.kr/default.do?menuId={menuId}&noti_id={noti_id}
  &noti_cont_id={noti_cont_id}&noti_no={noti_no}&bid_no={bid_no}
  &bid_rev={bid_rev}&g2b=Y&part={part}     (+물품이면 &remicon={rmcn_yn})
```

- 개찰결과 화면은 menuId 끝 001→002 (공사 NPRO11002 / 용역 NPRO12002 / 물품 NPRO13002).
- **default.do 를 쓰는 이유**: 알림 메일의 `appLogin.do?username=...` 방식은 SSO 로그인 엔드포인트라
  이미 로그인된 세션(타임아웃 30분)에서 재클릭하면 "로그인 실패"로 격회 실패한다. `default.do` 는
  비로그인 GUEST 진입이라 세션 충돌이 없다.
- **검증 상태**: 공사·용역·물품 3유형 모두 헤드리스 Chrome 실클릭으로 상세 렌더링(공고번호·공고명·첨부
  목록) 확인. 용역은 개찰결과 화면(NPRO12002)까지 검증.
- **렌더 확인 방법 주의**: 공고번호·공고명은 `<input>` value 로 렌더되어 `body.innerText` 에 안 잡힌다.
- **파라미터가 깨지면 조용히 목록 화면으로 떨어진다**: UUID 가 잘리거나 틀리면 오류 없이 "입찰공고
  목록" 화면이 뜬다(답변에 URL 을 `f5291ec3-...` 처럼 중간 축약해 보여준 것을 클릭해 발생한 실측).
  **딥링크는 항상 전체 URL 그대로 안내하고, 절대 중간을 `...` 로 줄여 표시하지 않는다.**
- **remicon 파라미터**: 물품에만 `rmcn_yn` 값을 전달. 파라미터명·필수 여부는 미실측 — 물품 링크
  오동작 시 1순위 점검 대상.
