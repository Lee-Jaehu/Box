# Worklog 데이터 스키마 & 개발자 간 인터페이스 정의 (v0.1)

작성: 2026-10-02 · 대상: Worklog 웹 개발(A) / 요약·PPT 파이프라인 개발(이재후)

> **시연 범위 안내 (2026-10-02 갱신)**
> - Daily 정리본(daily_summary), 변경 제안(change_proposal), 검토(review)는 운영 단계용으로 설계만 해 두고 시연에서는 만들지 않는다.
> - Daily마다 AI를 호출하지 않고, 주간 마감 때 원문을 한 번에 정리한다. 일정 변화는 weekly.json의 milestone_updates에 담아 PPT 생성 시 덧씌운다.
> - 아래 5장 흐름 중 시연에 쓰는 경로: Daily 저장 → 주간 마감(weekly + cumulative) → PPT 추출

---

## 1. 역할과 원칙

| 구분 | 개발자 A (Worklog 웹) | 이재후 (요약·PPT 파이프라인) |
|---|---|---|
| 하는 일 | 기준정보·Daily 입력 화면, JSON 적재, 사람의 승인·수정 화면 | Daily 정리, 변경 제안 추출, 주간 정리·누적 요약, PPT 추출 |
| 쓰는 폴더 | `master/`, `raw/` | `derived/` |
| 읽는 폴더 | `derived/proposals`, `derived/weekly` (승인 화면 표시용) | 전체 (읽기 전용) |

**원칙 4가지**
1. **한 파일은 한 사람만 쓴다.** A는 `master/`·`raw/`만, 이재후는 `derived/`만 쓴다. 서로의 파일을 고치지 않는다.
2. **기준정보는 웹에서만 바뀐다.** 파이프라인이 찾아낸 일정·상태 변경은 `derived/proposals`에 "제안"으로만 쓰고, 사람이 웹에서 승인하면 A가 `master/projects`와 `change_log`를 갱신한다.
3. **원문은 덮어쓰지 않는다.** Daily를 고치면 같은 파일의 `meta.revision`을 올린다. 파이프라인은 revision 변화로 재처리 여부를 판단한다.
4. **AI 결과는 사람이 확인한 것만 PPT에 쓴다.** 파일럿에서는 과제 책임자가 **주간 정리본**을 주 1회 확인한다 (Daily 정리본 개별 확인은 생략, 필요 시 `review.target_type = daily_summary`로 확장).

---

## 2. 폴더 구조

```
data/
├─ master/                         ← A
│  ├─ codes/code_table_site_process.json      (법인·공정 코드표)
│  ├─ codes/milestone_templates.json          (업무 유형별 마일스톤 템플릿)
│  └─ projects/{project_id}.json              (기준정보)
├─ raw/                            ← A
│  ├─ daily/{yyyy}/{yy-mm-dd}/{daily_id}.json (Daily 원문)
│  ├─ pics/{yyyy}/{yy-mm-dd}/...              (표 이미지·첨부, 표시용)
│  └─ reviews/{review_id}.json                (사람의 승인·수정 기록)
└─ derived/                        ← 이재후
   ├─ daily_summary/{daily_id}.json           (Daily 정리본)
   ├─ proposals/{proposal_id}.json            (기준정보 변경 제안)
   ├─ weekly/{project_id}/{week}.json         (주간 정리본)
   ├─ cumulative/{project_id}/{week}.json     (누적 요약)
   └─ ppt/{week}/...                          (추출 결과)
```

---

## 3. 스키마 목록

| 파일 | 작성자 | 단위 | 핵심 필드 |
|---|---|---|---|
| `project.schema.json` | A | 과제 1건 | 과제명·ID, 조직(그룹·담당·팀), 책임자·참여자·작성 대상자, 기간, 상태·건강도, 업무 유형(템플릿), 대상(법인·공정 코드), 배경, 목적, KPI, 마일스톤, 변경 이력, 완료 회고 |
| `daily.schema.json` | A | Daily 1건 | 날짜·태그(yy-mm-dd), 작성자, 과제 ID(없으면 개인 메모), 카테고리, 원문, **표(값)**, pics(표시용), 링크 |
| `review.schema.json` | A | 판단 1건 | 대상(주간 정리본/변경 제안), 대상 revision, 승인·수정·반려, 수정 값 |
| `daily_summary.schema.json` | 이재후 | Daily 1건 | 수행, 사실, 판단, 이슈, 다음 행동, 확인 필요 항목, 근거 ID, AI 실행 정보 |
| `change_proposal.schema.json` | 이재후 | 제안 1건 | 대상 경로, 이전 값 → 새 값, 사유, 마일스톤 매칭 후보·신뢰도, 상태 |
| `weekly.schema.json` | 이재후 | 과제 × 주차 | 헤드라인, 진행 현황, 향후 계획, 이슈, 변경 없음 여부, 분량 예산, 검토 상태 |
| `cumulative.schema.json` | 이재후 | 과제 × 주차 | 누적 요약, 고정 사실 목록, 갱신 방식(누적/재생성) |

모든 파일에 공통 `meta`가 있다: `schema`, `schema_version`, `revision`, `created_at`, `updated_at`, `updated_by`.

---

## 4. 공통 규칙

**ID 형식**

| 대상 | 형식 | 예시 |
|---|---|---|
| 과제 | `P-{팀약어}-{3자리}` | P-ASM-001 |
| Daily | `D-{yyMMdd}-{작성자}-{2자리}` | D-260922-ljh-01 |
| 마일스톤 | `M{n}` / 하위 `M{n}-{k}` | M6-3 |
| 변경 제안 | `CP-{yyMMdd}-{3자리}` | CP-260922-001 |
| 검토 | `R-{yyMMdd}-{3자리}` | R-260922-001 |
| 변경 이력 | `CH-{4자리}` (과제 내 일련번호) | CH-0007 |

**날짜·시간**
- 날짜는 `YYYY-MM-DD`, 시각은 KST ISO 8601 (`2026-09-22T11:00:00+09:00`).
- Daily의 `tag`(yy-mm-dd)는 화면·폴더용이고, 계산은 `date`를 쓴다. 둘은 항상 일치해야 한다.
- 주차는 ISO 주차(월~일), `2026-W39`. 주간 마감은 금요일 18:00 [확인 필요].

**코드**
- 법인·공정·라인은 `code_table_site_process.json`의 code만 저장한다. 화면은 이름을 보여주고 저장은 코드로 한다.
- 카테고리: `DEV`(개발·검증), `ROLL`(수평전개), `OPS`(운영·유지보수·문의), `INV`(투자·심의), `DATA`(데이터 분석), `RPT`(보고·교육·지원).
- 상태: 과제 `예정/진행/완료/보류/취소`, 건강도 `정상/주의/지연/판단 불가`, 마일스톤 `예정/진행/지연/완료/보류/취소`.

**파일 쓰기**
- UTF-8(BOM 없음), 들여쓰기 2칸.
- 임시 파일에 쓴 뒤 이름 변경(원자적 쓰기)으로 저장해, 읽는 쪽이 반쯤 쓰인 파일을 읽지 않게 한다.
- 저장할 때마다 `revision += 1`, `updated_at`, `updated_by` 갱신.
- 삭제는 파일을 지우지 않고 `deleted: true`(Daily) 또는 `active: false`(코드)로 표시한다.

**표 데이터**
- Daily의 표는 `tables[].columns / rows`에 **값으로** 저장한다. `pics`는 화면 표시용이며 AI 입력에 쓰지 않는다.

---

## 5. 처리 흐름

```
[A] Daily 저장 (revision n)
      │
      ▼  (파이프라인이 새 파일·revision 변화 감지)
[이재후] Daily 정리 → derived/daily_summary
      │      └ 일정·상태 변경 감지 → derived/proposals (state=pending)
      ▼
[A] 웹 "변경 제안" 화면에서 책임자 승인/수정/반려 → raw/reviews
      │      └ 승인 시 A가 master/projects 갱신 + change_log 추가 (proposal_id 기록)
      ▼
[이재후] 금요일 마감: 주간 정리본(weekly) + 누적 요약(cumulative) 생성 (review_state=draft)
      │
      ▼
[A] 웹 "주간 확인" 화면에서 책임자 승인/수정 → raw/reviews
      │
      ▼
[이재후] 승인된 주간 정리본 + 누적 요약 + 기준정보(마일스톤) → PPT 추출
```

**파란색 판정 (PPT)**
- 주간 정리본 항목의 `changed: true`, 이번 주에 승인된 변경 제안이 바꾼 마일스톤 값 → 파란색 RGB(0,0,255).
- 그 외 누적 요약·기준정보 값 → 검정.

**재처리 규칙**
- Daily revision이 바뀌면 해당 정리본을 다시 만든다 (`ai.input_revisions`로 비교).
- 검토(review)의 `target_revision`이 현재 대상 revision과 다르면, 대상이 바뀐 것이므로 다시 검토를 요청한다.

---

## 6. 개발자 A 체크리스트

- [ ] 과제 등록·수정 화면: 코드표 기반 선택(법인·공정·라인), 업무 유형 선택 시 마일스톤 템플릿 자동 펼침
- [ ] 마일스톤 확정 시 `baseline` 고정, 이후 수정은 `plan`만 변경하고 `change_log` 기록
- [ ] Daily 화면: 날짜(태그 자동), 과제 선택(미선택 = 개인 메모, `visibility=private`), 카테고리(선택), 본문, **표 입력(값 저장)**
- [ ] 변경 제안 승인 화면: `derived/proposals` 중 `pending` 표시 → 승인/수정/반려 → `raw/reviews` 저장 + 승인 시 기준정보 갱신
- [ ] 주간 확인 화면: `derived/weekly`의 `draft` 표시 → 승인/수정/반려 → `raw/reviews` 저장
- [ ] 모든 저장에 `meta.revision` 증가, 원자적 쓰기, 스키마 검증(`schemas/*.schema.json`)

## 7. 이재후 체크리스트

- [ ] `raw/daily` 감시(신규·revision 변경) → Daily 정리 (개인 메모 제외)
- [ ] 마일스톤 매칭·변경 제안 생성 (신뢰도·후보 포함)
- [ ] 금요일 마감 배치: 주간 정리본·누적 요약 생성, 분량 예산 적용
- [ ] 리뷰 결과 반영 후 PPT 추출 (양식 v2 칸 이름 매핑)
- [ ] 모든 산출물에 `ai.model / prompt_id / prompt_version / input_revisions` 기록

---

## 8. 결정이 필요한 항목

1. 주간 마감 시각 (금 18:00 가정)
2. 사용자 ID 체계 (사번 권장, 예시는 이니셜)
3. 저장소 방식: 공유 폴더 파일 vs DB (파일로 시작해도 이 스키마를 그대로 DB 테이블로 옮길 수 있음)
4. 파이프라인의 감지 방식: 주기적 폴더 스캔 vs 웹 저장 시 호출(이벤트)
5. Daily 정리본 개별 확인을 파일럿 이후 도입할지
6. MI1(ESMI1) 사업장 코드 확정
