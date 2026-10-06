# Worklog 데이터 모델 — 구현 기본안

논리 모델이다. 실제 migration/DDL을 생성한 상태가 아니다. DB snake_case, API/export camelCase를 기본으로 하며 변환은 schema 계층에서 수행한다. ID는 UUID string, 서버 timestamp는 UTC 저장/ISO8601 응답, 업무 날짜·기한은 Asia/Seoul 달력 날짜다. 예시는 +09:00로 표시한다.

## 1. 공통

변경 가능한 aggregate에는 `id, revision, created_at, updated_at, created_by, updated_by, deleted_at`을 적용한다. 사용자 ID는 선택 작성자 기반이지 인증된 주체가 아님. audit event에는 action, entityType/Id, before/after 또는 변경 필드, actorId, timestamp, operationId를 기록. 이벤트 자체는 append-only.

JSON 문서는 schemaVersion(예: 1.0), 문서 payload에는 documentVersion(예: 1)을 둔다. schemaVersion은 저장/출력 계약 버전, revision은 데이터 수정 횟수, documentVersion은 editor 구조 버전이다.

## 2. 기준정보·프로젝트

| 테이블 | 주요 필드·제약 |
|---|---|
| organizations | id, name, kind=division/team, parent_id; team은 담당 조직 참조, active |
| users | id, name, team_id, employee_number nullable, external_key nullable, active |
| projects | id, name, team_id required, owner_user_id required, is_short_term, status, start_date/end_date nullable, background_doc, purpose_doc, retrospective_doc |
| project_members | project_id, user_id; composite unique, 대표도 멤버로 포함 |
| milestones | id, project_id, name, description_doc, is_general, sort_order, status, planned_start/end, baseline_start/end, actual_start/end, baseline_confirmed_at |
| project_kpis | id, project_id, name, unit, baseline_value nullable, target_value nullable, direction=increase/decrease/target nullable, active |

사번 nullable; 제공된 비공백 사번은 조직 전체 unique를 제안하나 실제 명단 중복은 import에서 확인. 빈 문자열은 null. 동일 이름/팀 자동 동일인 판정 금지. 이름 변경/팀 이동 후에도 내부 ID 유지. 조직·사용자 참조 중 물리 삭제 금지, 비활성화 제공.

프로젝트 상태: preparing/in_progress/on_hold/completed/cancelled.
마일스톤 상태: planned/in_progress/on_hold/completed/cancelled.
일반 마일스톤은 is_general=true, 상태 planned 기본이나 일정/완료율에 계산하지 않음. project별 general 하나 unique(부분 unique index 등). 이름이 아니라 flag로 판단.

기준 일정은 확정 시 현재 계획 쌍 복사, 변경은 audit event 보존. 공용 간트의 milestone ID와 일지 자유 gantt item ID는 다른 namespace/타입. 프로젝트 선택과 참조 milestone project_id 일치 필수.

## 3. 일지·TASK·성과

| 테이블 | 주요 필드·제약 |
|---|---|
| daily_logs | id, project_id, author_id, work_date, lesson_doc, note_doc; UNIQUE(project_id, author_id, work_date) |
| log_tasks | id, log_id, milestone_id, milestone_snapshot, content_doc, performed_start/end, sort_order; status 없음 |
| log_collaborators | log_id, user_id, name/team snapshot |
| achievements | id, log_id, type=quantitative/qualitative, preset_key, title optional, content_doc, numeric_payload nullable, kpi_id nullable, kpi_snapshot nullable, measured_on, period_start/end, source_task_id nullable |
| log_tracker_refs | id, log_id, client_entry_id, tracker_type, tracker_id, original_snapshot, sort_order, hidden_at nullable; UNIQUE(log_id, client_entry_id) |

한 일지에 N개의 TASK. 별도 TASK title required 없음. titlePreview는 첫 텍스트에서 파생해 캐시 가능. performed 날짜 기본 work_date. 최소 하나의 기록이 있는 일지를 저장하는 검증을 권장하되 TASK가 없고 성과/메모만 있는 일지도 허용(구현 기본값).

author/project/milestone 표시값은 새 로그/TASK 작성 시 snapshot. 이후 기준정보 변경이 기존 snapshot을 덮어쓰지 않음. 연결 milestone을 명시적으로 바꾸면 그 TASK snapshot 갱신하고 이력 보존. 과거 일지 본문을 수정하는 것은 허용하므로 일지가 불변 archive라는 뜻은 아님.

numeric_payload 필드: metricName, beforeValue, afterValue, targetValue, value, unit, currency, comparisonBasis, measurementScope, frequency(optional), derived{difference, relativeChangePercent, percentagePointChange}, calculationVersion, summaryText. Decimal 계산/문자열 직렬화로 부동소수 오차 방지. preset별 허용/필수 필드를 discriminated schema로 검증. 계산된 값은 서버가 재계산, 사용자가 보낸 derived를 신뢰하지 않음. before=0의 relativeChangePercent null.

## 4. 트래커

| 테이블 | 필드 |
|---|---|
| todos | id, project_id, content_doc, assignee_id nullable, due_date nullable, status, source_log_id nullable, source_issue_id nullable |
| issues | id, project_id, content_doc, assignee_id nullable, due_date nullable, impact_doc nullable, response_doc nullable, status, source_log_id nullable |
| tracker_events | id, tracker_type/id, previous_status, next_status, result_doc nullable, actor_id, occurred_at, created_task_id nullable, operation_id |

To-Do 상태: open/in_progress/completed/cancelled.
Issue 상태: open/in_progress/resolved/closed.
기한 초과는 due_date와 상태로 계산. 일별 TASK→To-Do foreign key나 진행률 동기화 없음. tracker_events.created_task_id는 완료 출처/중복 방지용이며 지속적 업무 추적 연결이 아님.

일지의 original_snapshot은 첫 등록 당시의 내용/담당/기한. 이후 상태는 tracker 조회로 별도 표시한다. 일지 PUT에 refs가 누락됐다고 tracker 삭제하지 않음. 명시적 ref 숨김만 가능. tracker 삭제 시 출처 일지와 완료 TASK 유지, 현재 조회는 삭제 상태 표시.

Issue→Todo 생성은 project 일치, 원본 issue 삭제 시 source 참조는 tombstone으로 유지. To-Do 완료가 Issue 상태 변경을 유발하지 않음.

## 5. 첨부

| 테이블 | 필드 |
|---|---|
| attachments | id, project_id, original_name, stored_relative_path, media_type, size_bytes, sha256, width/height nullable, state=temp/committed, uploaded_by, uploaded_at |
| task_attachments | id, task_id, attachment_id, title nullable, description, sort_order |

본문 image node는 task_attachments.id(attachment use ID)를 참조한다. 바이너리와 사용처 메타데이터 분리. 이미지 description nonempty, 해당 task 소속 node만 참조 허용. 다른 프로젝트 attachment 임의 연결 금지. 복사 TASK는 동일 바이너리를 재사용할 수 있으나 새 task_attachment와 설명 snapshot을 만든다. 원본 파일과 usage metadata를 혼동하지 않음.

업로드는 temp 파일과 DB 메타만 생성. 일지 저장 시 task_attachment 연결과 committed 변경을 transaction 처리한다. 물리 파일은 이미 존재해야 한다. DB commit 뒤 final path 이동이 필수인 구조는 피한다. 파일 삭제는 모든 active/soft-deleted 참조와 백업 정책을 확인한 별도 정리에서만 수행.

## 6. 내부 테이블

- audit_events: 변경/기준 일정/삭제/복원 이력.
- idempotency_requests: key, scope, request_hash, response_json, completed_at, expires_at.
- export_jobs: unique target_key, requested_revision, exported_revision, attempts, next_attempt_at, last_error, status.
- export_targets: target의 단조 증가 sourceRevision(또는 job에 통합 가능). 업무 commit마다 관련 target revision 증가.
- import_previews: token/hash, validated normalized rows, base master revisions, expires_at; 오래된 preview commit은 재검증.
- backup_runs: 시작/완료/실패, 파일 경로, manifest, schema version.
- app_metadata: instance_id, schema/config metadata. 초안 서버 구분에 사용.

## 7. 본문 문서 계약

`{documentVersion:1, format:"tiptap-json", doc:{type:"doc",content:[...]}}`

허용 nodes 초기안: paragraph,text,heading,bulletList,orderedList,listItem,taskList,taskItem,table,tableRow,tableHeader,tableCell,image,gantt,hardBreak. marks: bold,italic,underline,strike,link 등 실제 채택분만. 이름 `taskList`는 에디터 체크리스트 node일 뿐 업무 TASK/To-Do 테이블과 관계없음. 링크 URL scheme allowlist.

image attrs: attachmentUseId, 표시 크기 optional. 설명은 task_attachments에 원본 저장, 렌더링 때 조회. 임의 외부 URL 이미지를 원본 대신 저장하지 않음.

gantt attrs: chartVersion, viewMode, items[{itemId,label,startDate,endDate,progressPercent?}], displayRange optional. chart item과 업무 TASK 식별자를 혼용하지 않음. 날짜는 YYYY-MM-DD, end 포함 의미를 adapter에서 통일, 일정 없는 항목의 렌더링은 UX 참조.

서버는 최대 문서 크기·깊이·node 수·이미지 개수 제한을 설정값으로 검증한다(초기값은 시제품에서 측정). 알 수 없는 node를 조용히 삭제하지 말고 422와 위치를 응답. HTML 저장을 canonical로 바꾸지 않음.

## 8. 내보내기 계약

daily: fileType=WORKLOG_DAILY_EXPORT, schemaVersion, documentVersion, generatedAt, sourceRevision, timezone, project{id,name,deletedAt}, date, logs[].
각 log는 id, author snapshot, revision, timestamps, tasks[], todoRecords[], issueRecords[], achievements[], lessonLearned, note, collaborators[].
tasks[]는 milestone snapshot, content, performed dates, attachments[]. 첨부는 data root 기준 fileRef 포함. 외부 전달 bundle은 실제 파일 포함 여부 manifest로 명시.

project: fileType=WORKLOG_PROJECT_EXPORT, 프로젝트 필드/조직/대표/참여자 snapshot, milestones, kpis.
trackers: fileType=WORKLOG_TRACKER_EXPORT, projectId, current todos/issues/events, sourceRevision.
master exports는 active/deleted 식별 가능. JSON 파일은 보관 이력 자체가 아니며 DB revision/audit와 구별.

예시는 `examples/` 참조. 식별자·본문·출력 관계를 보여주는 예시이며 Pydantic schema 구현·검증 완료를 의미하지 않는다.


---

## 구현 반영 (2026-10-04)

위 표는 설계 기준이며 실제 스키마는 `backend/app/models.py` 와 Alembic `0001_initial_schema` 가 원본이다. 설계와 달라진 점:

- **시간/날짜:** 서버 시각은 UTC 로 저장(SQLite 에는 naive UTC, 응답은 `...Z` ISO8601), 업무 날짜는 `DATE`. 내보내기 JSON 의 시각은 `Asia/Seoul`(+09:00)로 변환한다.
- `daily_logs.author_snapshot`(JSON): 작성자 이름·팀·사번과 `projectName` 을 일지 최초 작성 시 보존. `log_tasks.source_event_id`: 완료/해결 이벤트로 생성된 TASK 의 출처(지속 연결 아님).
- `log_tasks`/`achievements`/`log_collaborators`/`log_tracker_refs` 에는 `deleted_at`/`revision` 이 없다. 일지 전체 저장에서 빠진 TASK 는 삭제(일지 자체의 revision 이 변경 단위). 일지는 `deleted_at` 으로 휴지통 처리.
- `project_kpis.baseline_value/target_value` 는 **Decimal 문자열**(부동소수 오차 방지). 성과 `numeric_payload` 의 수치도 문자열이며 서버가 재계산한다(`derived`: `difference`, `improvement`, `improved`, `relativeChangePercent`, `percentagePointChange`, `attainmentPercent`, `achieved`).
- `export_targets` 는 `export_jobs` 에 통합: `requested_revision` 이 단조 증가하는 `sourceRevision`, `exported_revision` 은 실제로 파일에 쓴 revision.
- `idempotency_requests` PK 는 `(key, scope)`, `status_code`/`response_json` 저장, 기본 보관 30일.
- `backup_runs`: `kind`(daily/manual/pre_restore), `local_date`, 부분 unique index(`kind='daily'` 일 때 `local_date` 유일) 로 같은 날짜 중복 예약 방지.
- `app_metadata` 키: `instance_id`(서버 인스턴스), `restore_generation`(복원할 때마다 증가, 브라우저 초안 키에 포함).
- 부분 unique index: 조직 `external_key`, 사용자 `employee_number`/`external_key`(NULL 제외), 프로젝트당 일반 마일스톤 1개(`is_general`).
- `attachments.state`: `temp`(업로드 직후, 최종 경로에 이미 저장됨) → `committed`(일지 저장 시). 사용처는 `task_attachments`(`id` = 본문 image node 의 `attachmentUseId`, 클라이언트가 생성한 UUID 를 보존).
- 성과 프리셋 키는 `08_DECISIONS.md` I09 참조(예시 JSON 의 `time_reduction` 과 일치).
- (2026-10-04) `log_tasks.title` (nullable, 최대 200자) 추가 — Alembic `0002_task_title`. 기존 TASK 는 NULL(= 본문 첫 줄 요약).
