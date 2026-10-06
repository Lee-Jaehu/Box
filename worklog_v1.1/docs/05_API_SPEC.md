# Worklog API 계약 — 구현 기본안

Base `/api/v1`. JSON camelCase. 로그인 토큰 없음. 변경 요청에 `X-Actor-Id`로 선택 작성자 ID를 전달하고 존재/활성 상태만 검증한다. 이것은 인증이 아니다. UI와 API는 동일 Origin, 기본 CORS 전체 허용 금지.

## 1. 공통

- GET list: `items, nextCursor` envelope. 기본 limit=50, 최대 200 제안. 날짜/project/team/user/status 필터, stable sort.
- 변경: `expectedRevision` 필수(신규 0), `Idempotency-Key` 필수. 서버 시각/ID 관리.
- 성공: `{data:..., meta:{requestId, exportPending}}`. 목록은 data 내부 items/nextCursor.
- 오류: `{error:{code,message,fieldErrors?,currentRevision?,resourceId?},requestId}`.
- 404 not found, 409 revision/idempotency/restore conflict, 413 size, 415 unsupported media, 422 validation, 503 retryable storage busy.
- 응답 성공은 DB commit 기준. JSON export 상태와 구별.
- revision 조건부 update가 실패하면 409, 자동 last-write-wins 없음.
- project 삭제 중 하위 변경 차단은 서버에서도 검증.

## 2. 라우트 목록

| Method / path | 동작 |
|---|---|
| GET /health | 실행 상태; 내부 경로·민감 설정 반환 금지 |
| GET /app-info | instanceId, schemaVersion, timezone, 지원 기능 |
| GET/POST /organizations | 조직 목록/등록 |
| PATCH /organizations/{id} | 조직 수정·비활성화 |
| GET/POST /users | 사용자 목록/등록 |
| PATCH /users/{id} | 사용자 정보/비활성화 |
| POST /imports/masters/preview | Excel/CSV 업로드·열 연결·검증 |
| POST /imports/masters/commit | previewToken으로 원자적 적용 |
| GET /imports/masters/template | 가져오기 양식 다운로드 |
| GET/POST /projects | 목록·등록; 기본 general milestone 함께 생성. 목록·상세 항목에 `milestoneSummary {total, completed, cancelled}`(일반·수시 업무·삭제 제외, 왼쪽 트리 완료 표시용) |
| GET/PATCH/DELETE /projects/{id} | 상세·수정·휴지통 |
| POST /projects/{id}/copy | 선택 기준정보 복사, 새 IDs |
| GET/POST /projects/{id}/milestones | 목록·빠른 등록 |
| PATCH/DELETE /milestones/{id} | 수정·휴지통 |
| POST /milestones/{id}/confirm-baseline | 기준 일정 확정/재확정 |
| GET/POST /projects/{id}/kpis | KPI 목록·등록 |
| PATCH /kpis/{id} | 수정·비활성화 |
| GET /projects/{id}/logs?date=&authorId= | 해당 날짜 일지 찾기 |
| PUT /projects/{id}/logs/{date}/{authorId} | 일지 전체 신규/수정 저장 |
| GET/DELETE /logs/{id} | 일지 상세·휴지통 |
| GET/POST /projects/{id}/todos | 트래커 조회·직접 등록 |
| GET/PATCH/DELETE /todos/{id} | 상세·수정·휴지통 |
| POST /todos/{id}/complete | 완료 및 선택 TASK 생성 |
| POST /todos/{id}/reopen | 다시 열기 |
| GET/POST /projects/{id}/issues | 조회·직접 등록 |
| GET/PATCH/DELETE /issues/{id} | 상세·수정·휴지통 |
| POST /issues/{id}/todos | 연결된 대응 To-Do 생성 |
| POST /issues/{id}/resolve | 해결 및 선택 TASK 생성 |
| POST /issues/{id}/close | 종결 확인 |
| POST /issues/{id}/reopen | 다시 열기 |
| POST /attachments | multipart 임시 업로드; projectId 포함 |
| GET /attachments/{id}/content | 검증 후 inline image 또는 문서 download |
| GET /trash | 삭제 항목 목록 |
| POST /trash/{entityType}/{id}/restore | 복원·참조/고유 충돌 확인 |
| GET /exports/status?projectId= | 대상별 요청/완료 revision·지연·오류 |
| POST /exports/rebuild | 사본 재생성 요청; 202 |
| POST /exports/bundle | DB snapshot 기반 최신 프로젝트/기간 bundle |
| GET/POST /backups | 이력/지금 백업 |
| POST /backups/{id}/restore | 명시 확인 후 maintenance mode 복원 |

최소 범위로 구현하고 추상 CRUD generator보다 업무 동작의 일관성을 우선한다. 상태 변경 PATCH가 complete/resolve의 이력·원자성 규칙을 우회할 수 없게 한다.

## 3. 일지 저장 예시 형태

```json
{
  "expectedRevision": 4,
  "tasks": [
    {
      "id": "existing-or-client-generated-uuid",
      "milestoneId": "milestone-uuid",
      "content": {"documentVersion": 1, "format": "tiptap-json", "doc": {"type": "doc", "content": []}},
      "attachments": []
    }
  ],
  "newTodos": [{"clientEntryId": "stable-draft-uuid", "content": {"documentVersion": 1, "format": "tiptap-json", "doc": {"type": "doc", "content": []}}}],
  "newIssues": [],
  "hiddenTrackerRefIds": [],
  "achievements": [],
  "lessonLearned": null,
  "note": null,
  "collaboratorIds": []
}
```

위 UUID/빈 doc는 필드 구조 설명용이며 유효 저장 샘플 아님. 실제 예시는 examples/daily.example.json. 기존 tracker snapshot/current state는 GET으로 표시하고 PUT에서 수정하지 않음. 성공 응답은 정규화 전체 일지와 신규 tracker/ref ID 매핑, 새 revision 포함. 최종 필드명을 Pydantic/OpenAPI에 맞춰 문서 동시 갱신.

## 4. 완료/해결 예시

```json
{
  "expectedRevision": 2,
  "resultText": "협력사 수정본 재검증 완료",
  "appendToDailyLog": {
    "date": "2026-10-04",
    "authorId": "selected-user-uuid",
    "milestoneId": "milestone-uuid",
    "expectedLogRevision": 5
  }
}
```

appendToDailyLog=null이면 tracker만 완료, resultText 선택. append 시 비공백 결과 필수. 일지 미존재는 expectedLogRevision=0. tracker와 일지 둘 중 충돌이면 전체 409. 해당 일지 저장 중인 초안이 있으면 UI가 먼저 저장 또는 취소하도록 안내, 서버가 초안을 알 수 있다고 가정하지 않음.

중복 완료 POST의 같은 key는 이전 성공을 그대로 반환. 이미 완료 상태에서 다른 key로 같은 완료를 요청하면 상태 충돌로 거부하여 중복 TASK 생성 방지. 다시 열기 후 완료는 새 event, 신규 TASK는 사용자가 다시 선택한 경우만 생성.

## 5. 가져오기·업로드 계약

preview에 original row number, normalized values, new/update/ambiguous/error, error list, base revisions를 반환. 오류 행 하나라도 있으면 commit 불가. preview 만료/원본 목록 변경이면 재검증. 대량 import는 검증을 transaction 밖에서 끝내고 실제 적용만 짧게 transaction 처리.

파일 업로드는 저장 전에 20MB와 실제 media 검증. 단일 파일 업로드 실패가 일지 초안 삭제를 유발하지 않음. image caption 검증은 업로드 순간이 아니라 일지 정식 저장에서 수행하여 드롭 후 설명 입력 가능. 서버 temp attachment ID와 task draft ID를 매핑.

## 6. 날짜·삭제·오류 UX

서버가 소유권(project 일치)과 참조 유효성 검증. 선택 actor는 자기신고이며 다른 author 일지 수정 권한 제한은 없음. author 변경은 일반 PUT에 포함하지 않고 잘못된 기록 수정이 필요하면 명시적 별도 처리/복사로 제한(구현 기본값).

휴지통 log와 동일 고유키 신규 생성은 LOG_IN_TRASH로 409와 복원 대상 ID 제공. 상위 프로젝트 삭제는 PROJECT_IN_TRASH. DB locked는 제한 대기 후 retryable 503; 같은 Idempotency-Key로 재시도. 실제 서버 파일 경로·본문을 에러에 노출하지 않음.


---

## 구현 반영 (2026-10-04)

실제 계약은 `backend/app/api/routes.py`, `schemas.py` 가 원본이다(`/docs` OpenAPI 는 요청 스키마만 제공, 응답은 `{data, meta}` 봉투). 설계와 달라지거나 구체화된 점:

**공통**
- 변경 요청: `Idempotency-Key` 필수(없으면 422 `IDEMPOTENCY_KEY_REQUIRED`), 같은 key+같은 payload 는 이전 응답을 `meta.replayed=true` 로 재생, 다른 payload 는 409 `IDEMPOTENCY_KEY_REUSED`. 실패 응답은 저장하지 않으므로 같은 key 로 재시도할 수 있다.
- `X-Actor-Id`: 존재·활성 사용자만 검증(없으면 422 `ACTOR_REQUIRED`/`ACTOR_INVALID`/`ACTOR_INACTIVE`). **조직·사용자 등록/수정과 가져오기는 첫 사용자 부트스트랩을 위해 actor 없이도 허용**(있으면 검증).
- 복원 중에는 모든 변경이 503 `MAINTENANCE`. 저장소 혼잡은 503 `STORAGE_BUSY`(`Retry-After`), 같은 key 로 재시도.
- 삭제(`DELETE`)는 본문 없이 쿼리 `expectedRevision` 을 받는다. 생성은 201, `exports/rebuild`·`backups` 는 202.
- 요청 본문의 알 수 없는 필드는 422(조용히 무시하지 않음).

**일지** `PUT /projects/{id}/logs/{date}/{authorId}`
- `tasks[].id`·`tasks[].attachments[].id` 는 클라이언트 UUID(서버가 보존). `attachments[]` = `{id, attachmentId, title, description}`; 이미지 첨부는 `description` 필수(필드 오류 `tasks[i].attachments[j].description`), 본문 image node 는 같은 TASK 의 첨부 사용처를 가리켜야 함.
- 응답: 정규화된 전체 일지 + `trackerRefMap`(`clientEntryId → {refId, trackerType, trackerId}`). 기존 tracker ref 는 PUT 에 없어도 삭제되지 않고, `hiddenTrackerRefIds` 로만 숨김.
- 오류: 409 `LOG_EXISTS`(`resourceId`,`currentRevision`) / `REVISION_CONFLICT` / `LOG_IN_TRASH` / `PROJECT_IN_TRASH`, 422 `EMPTY_LOG` 등.
- `GET /projects/{id}/logs?date=&authorId=` 는 휴지통 일지도 `deletedAt` 과 함께 돌려준다(복원 안내용).

**tracker** `complete`/`resolve`: `resultText` 선택, `appendToDailyLog` 가 있으면 `resultText` 필수. 상태·이벤트·TASK·일지 revision·export dirty·멱등 응답이 한 트랜잭션. 이미 처리된 항목은 409 `STATE_CONFLICT`. `PATCH` 로는 `completed/resolved/closed` 를 설정할 수 없다. `GET /todos|issues/{id}` 는 `events` 이력 포함(Issue 는 `responseTodoIds`).

**첨부** `POST /attachments`(multipart `projectId`,`file`; `X-Actor-Id` 필요, `Idempotency-Key` 불필요). 20MB 초과 413, 허용 외 형식·실제 바이트 불일치 415, 픽셀 상한 413. 본문 이미지 표시용으로 `GET /attachment-uses/{useId}/content` 를 추가했다(`GET /attachments/{id}/content` 는 이미지 inline, 문서 attachment). 모두 `X-Content-Type-Options: nosniff`.

**가져오기** `POST /imports/masters/preview`(multipart `entity`=`organizations|users`, `file`, `encoding`) → `previewToken`, `summary`, `rows[]{row,action,values,errors,matchedId}`, `canCommit`. `commit` 은 `{previewToken}`; 오류/모호 행이 있으면 422 `IMPORT_HAS_ERRORS`, 명단이 바뀌었으면 409 `PREVIEW_STALE`, 이미 적용됐으면 409 `PREVIEW_CONSUMED`. 양식은 `GET /imports/masters/template?entity=&format=xlsx|csv`.

**운영** `POST /backups` 는 요청 안에서 바로 실행하고 결과 상태를 돌려준다. `POST /backups/{id}/restore` 본문은 `{"confirm":"RESTORE"}`. `GET /exports/status` 는 `pendingCount`/`failedCount` 와 대상별 상태. `POST /exports/bundle` 은 `exports/` 아래 zip(manifest 포함)을 만들고 삭제된 프로젝트는 409.

**업무일지 조회(프로젝트 횡단)** GET /logs?dateFrom=&dateTo=&projectId=&authorId=&teamId=&divisionId=&memberId=&status=&q= — 삭제된 일지·휴지통 프로젝트 제외, memberId = 대표이거나 참여자인 프로젝트. 항목에 `projectName`, `authorName`, `tasks[].titlePreview`, `todoCount`/`issueCount`/`achievementCount`. GET /logs/calendar?dateFrom=&dateTo=&…(같은 필터) → {days:[{date,count}]}.


**TASK 이름:** 일지 PUT 의 `tasks[].title`(선택, 최대 200자) / 응답 `tasks[].title`, `titlePreview`(이름 > 본문 첫 줄), 일지 조회 목록의 `tasks[].contentPreview`.


**한 파일 가져오기:** `POST /imports/masters/preview` 의 `entity=workbook`(xlsx 만) → `sections[{entity,label,summary,rows}]` 로 조직/사용자 시트를 구분해 반환(사용자 행 `values.teamName` 에 같은 파일의 새 팀 이름 포함). `commit` 응답에 `organizations`/`users` 별 건수 포함. 양식은 `GET /imports/masters/template?entity=workbook&format=xlsx`.


**보고자료(PPT)** — 작업은 서버 작업 스레드가 처리하고 화면은 상태를 조회한다. 응답 형식은 `{data, meta}` 동일.
- `GET /reports/config` → `aiMode`(`live`|`paste`), `aiModel`, `aiUrlConfigured`, `aiKeyConfigured`(키 값은 내보내지 않음), `fonts`, `maxProjects`.
- `POST /reports/jobs`(`Idempotency-Key`·`X-Actor-Id` 필요, 202) 본문 `{kind: weekly|period|monthly, template: weekly|exec, week:"2026-W40" | dateFrom,dateTo | month:"2026-10", projectIds[], orgLabel?, includeTables, includeGantts, includeMilestoneGantt, refreshAi, includeTeamSummary?, summaryAuthor?}`. 기간은 최대 366일, 프로젝트는 최대 30개.
  `includeTeamSummary`(기본 false, 화면은 기본 켜서 보냄)는 주간·기간 보고 + 주간업무 양식에서만 적용되고 그 밖에는 false로 저장된다. `summaryAuthor`(최대 40자)는 팀장 요약 페이지 작성자 칸(비우면 그 팀 첫 과제 담당자). 작업의 `options`에 그대로 돌려준다. 붙여넣기 모드에서는 과제마다 `promptId: project_summary`(`promptLabel` "팀장 요약") 응답을 한 번 더 묻는다. 형식 오류 422, 삭제·없는 프로젝트 409.
- `GET /reports/jobs?limit=` 최근 작업(프롬프트 원문 제외), `GET /reports/jobs/{id}` 상세. `status`: `queued`→`running`→`need_response`|`succeeded`|`failed`|`cancelled`. `need_response` 이면 `need{promptId, promptLabel, responseName, projectName, prompt, format}`.
- `POST /reports/jobs/{id}/response` `{responseName, text}` — 붙여넣은 AI 응답(설명 문장·```json 섞여도 됨)을 형식 검사 후 저장하고 다시 대기열로. 다른 단계 응답·JSON 아님 422(저장 안 함), 기다리는 응답이 아니면 409.
- `POST /reports/jobs/{id}/retry`, `POST /reports/jobs/{id}/cancel`.
- `GET /reports/jobs/{id}/files/{name}` — 결과 PPT, 검사 보고서(txt). 작업 결과 목록에 있는 이름만 내려준다.
