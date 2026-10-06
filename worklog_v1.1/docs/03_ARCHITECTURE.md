# Worklog 아키텍처

## 1. 배포·구성

개인 Windows PC 하나에서 수동 실행. 브라우저 → 동일 Origin FastAPI → SQLite/첨부 폴더. FastAPI는 빌드된 React 정적 파일과 `/api/v1`을 함께 제공한다. 개발 시 Node.js/Vite 사용, 배포물은 화면 빌드 결과를 포함하므로 운영 Node.js 불필요. 원격 SaaS/외부 CDN/AI API가 기본 동작에 필요하지 않다.

MVP 목표는 동시 작성 약 20명. 한 Uvicorn worker와 제한된 DB 연결로 시작한다(구현 기본값). CPU 집약 이미지 처리와 blocking 파일 작업을 이벤트 루프에서 장시간 실행하지 않는다. JSON exporter는 같은 프로그램 내 작업 루프로 실행, 별도 Redis/Celery/서버 없음. 서버 종료로 서비스가 멈추는 것은 의도한 운영이다.

## 2. 스택과 선정 상태

| 영역 | 방향 | 검증 |
|---|---|---|
| Frontend | React, TypeScript, Vite | 정확한 버전·빌드 결과 확인 |
| Editor | Tiptap 오픈소스 core/extensions | 한글 IME, 표, 체크리스트, 붙여넣기, JSON 왕복 |
| Gantt | Frappe Gantt + 자체 UI/adapter | 한글·드래그·리사이즈·날짜 경계 |
| Backend | FastAPI, Uvicorn, Pydantic | 동기 SQLAlchemy 호출과 작업 스레드 분리 |
| DB | SQLite, SQLAlchemy 2.x, Alembic | 런타임 SQLite 버전, WAL, 마이그레이션 |
| Import | openpyxl, Python csv | 문자열 사번·오류 전량 검증 |
| Draft | IndexedDB | 새로고침·수정 충돌·저장 중 입력 |
| Image metadata | Pillow 등 로컬 라이브러리 후보 | 실제 바이트/해상도 검증, 과대 이미지 방어 |

Tiptap 오픈소스 코어 라이선스와 각 채택 확장 라이선스를 확인·고지한다. 유료/클라우드 기능은 전제로 삼지 않는다. Frappe Gantt의 정확한 배포 버전·라이선스도 고정 전에 확인한다. 선택 도구가 필수 UX를 충족하지 못하면 adapter 경계 안에서 대체하고 원장에 이유 기록. 검증되지 않은 버전을 ‘고정 완료’라고 쓰지 않는다.

## 3. 권장 모듈

```text
worklog/
  backend/app/
    main.py
    api/                 # router, request/response, errors
    services/            # project, log, tracker, import, export, backup
    repositories/        # SQLAlchemy queries, transactions
    models/              # ORM tables
    schemas/             # Pydantic, document/export contracts
    workers/             # durable export jobs consumer
    storage/             # attachment, atomic JSON write, backup
  backend/migrations/
  frontend/src/
    features/            # identity, masters, projects, logs, trackers
    editor/              # Tiptap nodes, table UI, document converters
    gantt/               # canonical schedule adapter
    api/
    drafts/
  frontend/dist/         # build artifact for distribution
  scripts/               # setup, run, backup, restore, validate
  tests/
  docs/
  runtime/python/        # optional embedded runtime; not source dependency
  data/                  # never overwrite on update
  config/
  실행.bat
```

배포 실행기 파일명은 `실행.bat`로 한다. 한국어/공백 경로를 지원한다.

## 4. DB 설계 원칙

- relational: 프로젝트/조직/사람 관계, 일지 날짜, 상태, 담당, 마감, 버전, 검색 인덱스.
- JSON column: 지원 문서 트리, 자유 간트 내용, 성과 프리셋 payload. 임의 전체 서비스 JSON 단일 컬럼 저장 금지.
- 모든 연결은 내부 UUID. employeeNumber optional, name 식별자 아님.
- Foreign keys ON. WAL 사용. busy_timeout 초기 5초, synchronous FULL 제안. 실제 부하와 내구성 요구에 따라 명시적으로 검증·조정.
- local disk only; live DB를 네트워크 공유/동기화 폴더에서 운영하지 않음.
- 요청별 session/transaction. 한 전역 SQLAlchemy session 공유 금지. 버전 비교와 update는 같은 transaction에서 조건부 update.
- transaction 중 대용량 파일 변환·백업·전체 JSON 생성 금지.
- 기본 일지 UNIQUE(project_id, author_id, work_date). soft-deleted row도 기존 identity를 유지하며 재생성 대신 복원 안내.

## 5. 핵심 트랜잭션

### 일지 전체 저장

actor와 데이터 참조·문서·첨부 검증 → Idempotency-Key 확인 → expectedRevision 조건부 변경 → 신규 TASK/성과/등록 요청 반영 → 신규 To-Do/Issue 생성 및 출처 스냅샷 연결 → 정식 첨부 연결 → 변경 이력·export job 기록 → commit → 새 revision 응답.

생성은 revision=0/미존재 조건, 날짜 unique 경쟁은 기존 일지 반환 정보와 409. 기존 tracker reference는 read-only: 클라이언트 전체 일지 PUT이 기존 tracker 현재 상태를 덮어쓰지 못하게 한다. 서버 원본 스냅샷은 보존하고 일지 내 표시 제거만 별도로 구분한다.

### To-Do 완료 / Issue 해결 + 오늘 한 일

tracker revision 검증. append 요청 시 대상 일지 revision도 확인. 현재 선택 사용자·대상 날짜·같은 프로젝트 마일스톤 검증. 상태/선택 결과 event + TASK + 일지 revision + export dirty + 멱등 응답을 하나의 transaction으로 commit. 하나라도 실패하면 전부 rollback. 사용자 편집 중인 일지를 서버가 몰래 병합하지 않으며 화면은 초안을 유지하고 충돌을 안내한다.

append=false면 결과 선택. append=true면 결과 본문 필요. 반환값은 생성 TASK와 변경된 일지 ID/revision. 완료 후 생성된 TASK는 독립 기록이며 tracker 재개/수정이 이를 바꾸지 않음. 완료 event → createdTaskId 출처는 보존하되 지속 관리 연결로 쓰지 않음.

### 멱등성

동일 key + 동일 payload hash이면 이전 결과 반환. 같은 key에 다른 payload면 409. 요청 처리와 결과 저장을 같은 DB transaction에 둔다. 일지에서 tracker를 생성하는 clientEntryId에도 UNIQUE(source_log_id, client_entry_id)를 적용하여 새로운 재시도 key만으로 중복 생성되지 않게 한다. 보관 기간은 설정 기본 30일, 적용 전 대상 데이터의 source uniqueness로 장기 중복 방지.

## 6. JSON exporter

DB가 원본이고 exporter 실패가 이미 commit된 일지를 취소하지 않는다. 업무 변경 transaction에서 `export_jobs(target_key, requested_revision, ...)`를 upsert한다. key는 project metadata / project+date daily / project trackers / master 등.

단일 exporter가 동일 대상의 작업을 합쳐 처리한다. 짧은 일관된 read transaction에서 해당 대상 데이터·sourceRevision를 함께 취득 → DB read 종료 → 문서 변환·파일 쓰기 → 같은 폴더 임시 파일 flush/fsync → replace. 파일 생성 완료한 revision만 처리 완료로 표시. 작업 중 최신 revision이 더 생겼다면 pending 유지. 파일 교체 후 프로세스 종료되어도 동일 내용을 다시 내보내는 것은 안전하다.

오류는 attempts/lastError/nextAttemptAt 기록하고 제한된 backoff 재시도. 종료 시 미완료 작업은 DB에 남으며 다음 수동 실행에서 재개. export status API와 수동 재생성. 정상 시 수초 내 목표지만 보장 SLA 아님. JSON 파일 안 sourceRevision/generatedAt 표시.

프로젝트 삭제는 project.json deletedAt 갱신, 일지 삭제는 해당 날짜 재생성, 날짜에 기록이 0개라도 daily.json은 빈 logs+버전으로 교체하여 낡은 데이터가 남지 않게 한다. 일반 소비자는 project tombstone/삭제 상태를 먼저 확인. 보고용 bundle은 DB에서 일관된 snapshot을 만들어 별도 생성하여 여러 사본 파일을 무조건 최신이라고 묶지 않는다.

## 7. 원본·출력 경계

Tiptap 허용 node/mark 목록과 `documentVersion`을 정의하고 validated JSON을 보존한다. 자유 간트는 custom node attrs의 독립 schedule 구조로 저장. 공용 마일스톤과 자동 양방향 연결 없음.

후속 변환은 Document→AIReadable / Document→HTML / Table→native PPT table / Gantt→SVG/PNG 등 별도 adapter. MVP에서 모든 PPT renderer 구현하지 않음. 본문 HTML 원본 저장이나 SVG/PNG만 남기기 금지.

## 8. 범위에 맞는 안전·운영

auth 없음은 명시하되 path traversal 차단, UUID 서버 검증, MIME/크기 확인, 안전한 HTML 렌더링, 첨부 다운로드 경로 검증은 적용. 데이터 폴더 전체를 정적 경로로 노출하지 않는다. 상대경로 첨부 참조는 서버가 검증해 해석. API 선택 actor는 감사 힌트이며 인증 정보 아님.

로그는 operation/request id·시간·실패 원인 중심, 본문·첨부 전체 불필요 출력 금지. 로컬 환경만으로 정상 동작. 실제 사내 접속은 IP/Windows 방화벽/네트워크 허용 상태를 운영자가 확인해야 하며 실행기가 방화벽을 임의 변경하지 않음.

## 9. 참고한 공식 문서

설계 참고이며 정확한 버전 확정과 실제 테스트는 후속 작업이다.
- https://fastapi.tiangolo.com/deployment/concepts/
- https://tiptap.dev/docs/editor/extensions/nodes/table
- https://github.com/ueberdosis/tiptap/blob/main/LICENSE.md
- https://docs.frappe.io/gantt/config
- https://github.com/frappe/gantt
- https://www.sqlite.org/whentouse.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/backup.html
- https://docs.sqlalchemy.org/en/20/dialects/sqlite.html
- https://docs.pydantic.dev/latest/concepts/models/
