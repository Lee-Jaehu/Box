# WorkLog 연동 (업무기록 시스템 export → 주간 정리·PPT·보고 자료)

> 2026-10-04. 동료가 만든 WorkLog(업무기록 작성 → JSON 적재·관리)의 export를 그대로 읽어 쓴다.
> 코드: `weekly_report/worklog.py`(변환), `weekly_report/sources.py`(입력 읽기), 대응표 `config/worklog_mapping.json`.
> 기존 내부 형식(data/master, data/raw/daily)도 함께 동작한다.

## 1. 파일 위치와 구분

- 위치: `config/sources.json`의 `worklog_dirs`(기본 `data/worklog`) 아래 어디든 둔다(하위 폴더 포함).
  - 예: `data/worklog/{과제 폴더}/project.json`, `data/worklog/{과제 폴더}/2026-10-04.json`
- 파일 이름이 아니라 JSON의 `fileType`으로 구분한다.
  - `WORKLOG_PROJECT_EXPORT`: 과제 기준정보
  - `WORKLOG_DAILY_EXPORT`: 날짜별 업무일지
- 같은 과제의 project export가 여러 개면 `generatedAt`(같으면 `sourceRevision`)이 가장 최근인 것을 쓴다.
- 같은 날짜의 업무일지 export가 두 개 있으면 기록 ID가 겹치므로 오류로 알린다(최신 파일만 두기).
- 원본은 읽기만 하고, 변환은 메모리에서 한다. 결과는 기존과 같이 `data/derived`·`output`에만 쓴다.
- 지원 `schemaVersion`: 1.0. 다른 값이면 같은 구조로 가정하고 경고한다.

## 2. 과제(project export) → 내부 기준정보

| WorkLog | 내부 | 규칙 |
|---|---|---|
| project.id (UUID) | project_id | 그대로 사용(스키마에 UUID 허용). mock 응답·derived 경로도 UUID |
| name | name | |
| team.parent.name / team.name | org.group·dept / org.team | 슬라이드 제목 "과제 진행 현황_{팀}" |
| owner, members (이름·사번) | owner, members, **people** | 이름은 export 값 사용(config/people.json보다 우선). 직급이 없어 이름만 표시 |
| status | status | `config/worklog_mapping.json` (preparing·planned → 예정, in_progress → 진행, completed → 완료 …). 모르는 값 → 진행 + 경고 |
| startDate / endDate | period.start / target | target_text = "'26.10" |
| background / purpose (tiptap) | background / purpose | 한 줄로: 글머리 목록은 " / ", 번호 목록은 "① ②" |
| milestones | milestones | 아래 표 |
| kpis | kpis | 형식 미정 → 아직 변환하지 않음(경고). KPI 칸 "-" |
| (없음) | health | **Rule 계산**: 계획 종료일 지남·미완료 단계가 있으면 지연, 계획 > Baseline이면 주의, 그 외 정상, 단계 없으면 판단 불가 (기준일 = generatedAt) |
| (없음) | target (대상) | **팀명으로 대체** (target_label, 사용자 결정) |

마일스톤

| WorkLog | 내부 | 규칙 |
|---|---|---|
| isGeneral=true ("일반·수시 업무") | — | 일정 표에서 제외. 그 단계의 업무일지는 주간 정리에 그대로 들어감 |
| deletedAt | — | 제외 |
| sortOrder | milestone_id M1, M2 … / order | 표 순서. 원본 UUID는 source_id에 보관(주차 비교 키) |
| plannedStart~plannedEnd | scope_label | **적용 범위 열 = 계획 기간 "10/01~10/04"** (사용자 결정) |
| baselineEnd / plannedEnd / actualEnd | baseline / plan / actual | Baseline이 아직 없으면 "–", 지연 일수 계산 안 함 |
| status | status | planned → 예정, in_progress → 진행, completed → 완료. 미완료이면서 계획 종료일이 지나면 **지연**(코드 판정) |

## 3. 업무일지(daily export) → 내부 Daily

- **log 1건(작성자 1명의 그날 기록) = Daily 1건**
- 기록 ID: `D-YYMMDD-{사번}-NN`(사번이 없으면 작성자 UUID 앞 8자리)
  - 같은 입력이면 항상 같은 ID가 나온다.
  - 날짜가 ID에 들어 있어 문장 끝 진행 날짜 "(10/04)"의 근거가 된다.
  - 원본 UUID(log·task·record)는 source_refs에 보관한다.
- 본문은 구조를 살려 아래처럼 만들고, AI 입력과 의미 검증(수치·날짜)의 근거로 쓴다.

```
[수행] (설계) AI 기반 프롬프트 구체화 (10/04)        ← task: (연결 마일스톤) 제목 (수행 기간)
  - GPT, Claude를 활용하여 개발 요건 구체화          ← task 내용 (tiptap 목록 그대로)
[이슈] 업무용 컴퓨터 Codex 사용 불가 (상태 미해결)   ← issueRecords (상태·담당·기한·영향·대응)
[할 일] Claude 개발 버전 테스트 (상태 미해결)        ← todoRecords
[성과] …  [배운 점] …  [비고] …  [협업] 이름(팀)     ← achievements, lessonLearned, note, collaborators
```

## 4. 마일스톤 = WorkLog 기준 (사용자 결정)

- 일정·상태는 WorkLog 값을 그대로 쓴다. AI 일정 추출은 쓰지 않는다.
  - weekly_rollup 프롬프트의 `{{milestone_policy}}`가 "항상 []"로 바뀐다.
  - AI가 값을 보내도 무시하고 검증 보고서에 남긴다.
- 주간 정리본(weekly JSON)에 그 주의 마일스톤 값 `milestone_snapshot`을 저장한다.
- 다음 주에는 **지난주 snapshot과 다른 값만** 코드가 `milestone_updates`로 기록하고, PPT에서 파란색으로 표시한다(계획·실적·상태).
  - 첫 주는 비교 대상이 없어 파란색이 없다.
- 과거 주차 PPT를 다시 만들면 그 주 snapshot 값으로 표를 만든다.

## 5. 동료에게 요청할 사항 (있으면 PPT가 더 정확해짐)

| 요청 | 이유 |
|---|---|
| 과제 **대상**(법인·라인·공정 등)·마일스톤 **적용 범위** 필드 | 지금은 팀명·계획 기간으로 대체 중 |
| **KPI 형식**(이름·단위·기준·목표·기간별 실적·방향) | 보고 자료 KPI 표·변화량(Δ, 개선/악화 색) 계산 |
| **achievements 형식** | 지금은 tiptap/문자열/레코드 형식을 추정해 처리 |
| 상태 값 **전체 목록**(과제·마일스톤·레코드) | 대응표에 없는 값은 경고 후 기본값 |
| log·task·record **삭제 표시**(deletedAt) | 삭제된 기록이 주간 정리에 들어가지 않게 |
| 짧은 **과제 코드**(예: P-QDX-001) | 파일 이름·화면 표시가 UUID보다 읽기 쉬움 |
| record의 **현재 상태**(originalSnapshot 외) | 이슈 해결 여부를 주간 보고에 반영 |
| 마일스톤 Baseline 확정 이력 | 일정 지연(+n일) 계산 근거 |

## 6. 예시 데이터

- `data/worklog/WorkLog-sample/`: 공유받은 export와 **같은 구조의 익명 예시**다. 이름·사번·UUID·팀은 가상 값이다.
  - 2026-10-01, 10-04 업무일지가 있다.
  - 저장소 규칙(실제 사내 데이터 금지)에 따라 받은 원본은 넣지 않았다.
- 데모: `python demo/run_demo.py demo/worklog 00000000-0000-4000-8000-000000000001 2026-W40` → `demo/worklog/out/`
- 웹 화면: 과제 목록의 "[WorkLog] WorkLog"를 고르면 된다. 업무일지는 읽기 전용이다(수정은 WorkLog 웹에서).
