# Worklog 결정원장

기준: 2026-10-04 사용자 설계 협의. 이 문서는 최신 확정 상태를 기록한다. 이전 자료의 방향과 충돌하면 아래 확정 사항을 우선한다.

## A. 확정 요구사항

| ID | 결정 |
|---|---|
| D01 | 독립 신규 Worklog. 기존 다른 업무 시스템의 코드/도메인 재사용 전제 없음 |
| D02 | 이메일 연동 아님. 프로젝트별 매일 기록은 의무 아님, 여러 담당자가 독립 작성 |
| D03 | 프로젝트→마일스톤→TASK. 프로젝트/마일스톤 기준정보, TASK는 매일 새 수행 기록 |
| D04 | 같은 프로젝트+작성자+날짜는 기존 일지 이어 쓰기. 한 일지에 여러 TASK/마일스톤 |
| D05 | TASK 이름 필수 아님, 제목 preview 가능. TASK 상태 없음 |
| D06 | 마일스톤 Master와 일지 화면에서 추가. 일반·수시 업무 기본 제공 |
| D07 | 프로젝트 팀 하나, 대표 1명+참여자 여러 명. 필수 이름·조직·대표, 작성자≠대표 가능 |
| D08 | 단발성 토글로 상세 입력 숨김, 기존 값 보존. 조직/담당자/상태 필터 |
| D09 | 사이트 상단 사용자 설정, 로그인/권한 아님. 사번 선택, 내부 ID로 식별 |
| D10 | 조직/사용자 기준정보와 Excel/CSV import, 미리보기, 오류 시 전체 적용 중단 |
| D11 | 계획/확정 기준/실제 시작·종료 일정. 기준 확정은 명시적 동작 |
| D12 | Word/Notion 같은 리치 편집, 마우스 표·간트 조작, 사용자 Markdown 문법 불필요 |
| D13 | 구조화 문서 JSON 원본, Markdown/HTML/이미지 파생. 공용/일지 자유 간트 모두 지원 |
| D14 | 이미지 TASK 바인딩·상세 설명 필수. 일반 문서 다운로드 첨부, 20MB/파일 |
| D15 | 일지 추가 섹션 To-Do/Issue/성과/Lesson Learned/메모/협업자 |
| D16 | To-Do/Issue 프로젝트 단위 별도 화면. 일지 첫 저장 때 등록, 이후 독립 수정 |
| D17 | 일지는 당시 tracker 내용 보존, 현재 상태 별도 표시. 일지 삭제가 tracker 삭제 아님 |
| D18 | Issue에서 대응 To-Do 선택 생성. To-Do 완료가 Issue 자동 해결 아님 |
| D19 | 매일 TASK와 To-Do 지속적 연결 안 함. 완료/해결 때 선택적으로 TASK 생성 |
| D20 | 완료 결과 한 줄 선택; TASK 추가 선택 시 결과 입력 필요. 마일스톤 선택, 현재 사용자 기본 |
| D21 | 완료/해결 재개 가능, 과거 이벤트·TASK 유지 |
| D22 | 정량/정성 프리셋과 안내. 정량 KPI 연결 선택, KPI 자동 덮어쓰기/무조건 합산 금지 |
| D23 | 일지 전체 저장. IndexedDB 초안 보존, 충돌 시 자동 덮어쓰기/병합 안 함 |
| D24 | soft delete/휴지통·복원. 완료/보류 프로젝트 기록 허용, 휴지통 프로젝트는 차단 |
| D25 | SQLite 원본 + data/json 프로젝트/날짜 사본 자동 생성. 사본→DB 자동 동기화 없음 |
| D26 | JSON 갱신 durable jobs, 실패 재시도, 원본 저장 상태와 구분 |
| D27 | 개인 Windows PC, MVP 동시 약 20명. 300명은 후속 가능성 |
| D28 | 수동 실행.bat, Conda→embedded→venv. 자동 부팅 시작/서비스/자동 재시작 제외 |
| D29 | data 경로 기본 프로그램 아래, 설정 가능. 운영 Node 불필요, 개발 빌드에만 사용 |
| D30 | 실행 중 하루 첫 저장 이후/수동 backup, 성공 최근 14개. 휴지통 자동 영구 삭제 없음 |
| D31 | 후속 요약 agent/PPT Generator는 MVP 밖. 읽기 쉬운 JSON과 이미지 문맥으로 확장 지원 |

## B. 철회/대체된 안 — 재도입 금지

- 사번 필수·사번 폴더 키 → 내부 userId, 사번 nullable.
- 사용자/날짜 파일만 원본 → SQLite와 프로젝트/날짜 export.
- Markdown 영구 원본 강제 → 편집 가능한 structured document JSON.
- TASK 마스터·기존 프로젝트 TASK에 매일 덧붙이기 → 일별 새 TASK.
- TASK 진행/완료 필수 → 상태 없음.
- To-Do에 여러 날 TASK 상시 연결 → 선택적 완료 시 결과 TASK만 생성.
- To-Do 완료 시 일지 기록 기능 전체 제거 → 최신 의견으로 선택적 완료 기록 복원.
- 첫 작성자=프로젝트 대표 → 명시 대표 선택, 별도 등록자.
- 다중 팀 공동 프로젝트 → 팀 하나.
- 300명 MVP → 20명 MVP.
- Windows 자동 시작·자동 재시작 → 수동 운영.
- 운영 Node 서버·CDN → 빌드된 static assets, FastAPI 제공.
- PPT까지 초기 필수 구현 → 후속 단계.

## C. 구현 기본값 (확정 요구와 구별)

이 값들은 다음 Codex가 별도 승인 반복 없이 선택·검증·수정할 수 있다. 변경 시 이유 기록.

- Conda env `worklog`, embedded `runtime/python/python.exe`, venv `.venv/Scripts/python.exe`. 순서는 확정, exact 이름은 기본값.
- React/TS/Vite, Tiptap, Frappe Gantt, FastAPI/Uvicorn, SQLAlchemy2/Alembic/Pydantic, openpyxl; exact 버전 미고정.
- 단일 Uvicorn worker, SQLite WAL/FK ON/busy_timeout 5s/synchronous FULL.
- 임시 첨부 7일, request idempotency 30일. 참조 중 정식 파일은 자동 삭제 안 함.
- API 경로·camelCase·테이블명, 문서 envelope, JSON schema 1.0은 상세 설계안.
- 수동 restore를 위한 maintenance mode, snapshot+첨부 manifest.
- 일반 항목 삭제 금지, 빈 로그 허용 최소 기준, 취소 프로젝트 기록 안내 후 허용.
- 프로젝트 복사 시 일지/실적/첨부/이력 제외. definitions 선택 복사.
- active log 삭제 고유키 재생성 대신 복원 안내.
- 표 cell merge/basic paste 최소 보장, 복잡한 spreadsheet formatting/간트 dependency UI 후속.
- 성능 p95 2초/JSON 5초는 시험 초기 목표이며 보장 아님.

## D. 남은 검증 (새 제품 승인 질문이 아님)

1. Windows Python/architecture와 embedded 패키징·한글 경로. — **부분(2026-10-04)**: Windows 11 x64 + Python 3.12.14 에서 런처 선택·한글/공백 경로의 선택·앱 오류 처리 확인. **embedded 패키징 미검증**, 서버 전체 구동은 ASCII 경로만.
2. Tiptap 한글 IME·table JSON·gantt custom node, Frappe 날짜 포함/타임존. — **부분**: table JSON(병합 속성)·custom node 왕복·Frappe 날짜 계약(포함 종료, 로컬 날짜) 확인. **한글 IME 실제 조합 미검증**.
3. exact 의존성/라이선스/오프라인 자산 목록. — **완료**: `requirements.txt`, `package.json`(정확 고정)+lock, `THIRD_PARTY_NOTICES.md`, 오프라인은 `make-wheelhouse.ps1`/`setup-venv.ps1 -WheelDir`(wheelhouse 생성은 온라인 설치로 간접 확인, 오프라인 설치 자체는 미실시). 법무 검토 아님.
4. 실제 20명 workload, 큰 표·첨부·backup/export 동시 실행. — **부분**: 20 스레드 혼합 부하·동시 저장 정합성 확인(이 PC). 큰 표/20MB 동시 업로드/백업 중 저장은 미실시.
5. DB restore/JSON 재생성/중복 요청 failure injection. — **완료**: 백업 복원, JSON 삭제 후 재생성, export 교체 실패/재시작, 완료+TASK fault injection, 멱등 재전송, 실제 프로세스 강제 종료.
6. 운영 PC 네트워크 접속·방화벽·설치 가능 환경. 환경 접근이 없으면 미검증 표시. — **미검증**(localhost 만). [11_WINDOWS_SMOKE.md](11_WINDOWS_SMOKE.md) 로 이관.

## E. 이후 변경 기록 형식

날짜 / 결정 ID / 변경 이유 / 사용자 요구 또는 구현 근거 / 영향받는 문서·migration / 검증 결과를 남긴다. 이전 확정 사항을 몰래 수정하지 않는다.

## F. 구현 중 확정·조정한 사항 (2026-10-04)

확정 요구(A)는 바꾸지 않았다. 아래는 구현 기본값(C)을 검증하며 정하거나 조정한 것이다. 형식: ID / 변경 이유 / 근거 / 영향(문서·migration) / 검증.

| ID | 결정 | 이유·근거 | 영향 | 검증 |
|---|---|---|---|---|
| I01 | 쓰기는 **프로세스 내 mutex + `BEGIN IMMEDIATE`**, 읽기는 별도 엔진(락 없음) | SQLite busy handler 가 순서 없는 polling 이라 20명 동시 저장에서 일부 요청이 수 초 굶음(극단 시나리오 p95 4.4s/max 6.0s → 2.2s/2.3s). 단일 worker 전제와 일치 | `db.py`, migration 없음 | `test_concurrency.py`, `test_logs.py`(동시 생성/수정), 부하 4회 |
| I02 | `synchronous=FULL` **유지** | NORMAL 로 바꿔도 저장 시간 개선 없음(40ms 내외, CPU 바운드). 내구성을 낮출 이유가 없음 | 설정 키 `SQLITE_SYNCHRONOUS` 만 열어 둠 | 프로파일 4회, 부하 |
| I03 | 문서 envelope 의 **서버 검증 규칙 = 프런트 규칙 동일**(허용 node/mark, 링크 http/https/mailto, 간트 항목, 크기·깊이·node 수) | 알 수 없는 node 를 조용히 삭제하지 않고 위치와 함께 422 | `documents.py` | `test_logs.py`, `roundtrip.test.ts` |
| I04 | **TASK ID 와 첨부 사용처(attachmentUseId)는 클라이언트가 UUID 로 생성**하고 서버가 보존 | 서버 저장 중에도 입력을 계속할 수 있고, 재전송/응답 유실에도 본문 image node 와 사용처 연결이 유지됨 | API 계약(§05 구현 반영) | `logDraft.test.ts`, `test_attachments.py` |
| I05 | 첨부는 업로드 시 **최종 경로에 저장 + state=temp**, 일지 저장은 state 만 committed | “DB commit 뒤 파일 이동”이 필요 없는 구조 | `attachments.py` | `test_attachments.py` |
| I06 | 간트 날짜: **포함 종료일, 로컬 달력 날짜(YYYY-MM-DD)**. Frappe `end` 자정=+24h, 콜백 `end`=배타−1초 를 어댑터에서 변환. UTC 변환 금지 | Frappe 1.2.2 소스 확인 + 브라우저 실측 | `gantt/adapter.ts` | `adapter.test.ts`, 브라우저 |
| I07 | Frappe Gantt CSS 를 `frontend/src/vendor/` 로 복사 | 패키지 `exports` 가 CSS 서브패스를 열지 않아 import 불가(MIT 고지 포함) | `THIRD_PARTY_NOTICES.md` | 빌드 |
| I08 | Tiptap 구성: StarterKit 에서 codeBlock/blockquote/horizontalRule/code 비활성(허용 node 목록과 일치), Link 는 http/https/mailto | 허용 node 외 구조가 저장되는 것을 막음 | `editor/schema.ts` | `roundtrip.test.ts` |
| I09 | 성과 프리셋 키: `time_reduction`, `cost_reduction`, `throughput_increase`, `defect_reduction`, `goal_achievement`, `custom` / 정성: `standardization`, `quality_stability`, `risk_prevention`, `collaboration`, `usability`, `knowledge`, `custom`. `calculationVersion` 은 문자열 `"1"` | `examples/daily.example.json`(`time_reduction`, `"1"`)과 일치. `improvement`(좋은 방향 양수)·`improved` 를 추가해 악화를 개선으로 포장하지 않음 | `achievements.py` | `test_achievements.py` |
| I10 | 사번 셀이 **숫자 형식이면 오류**(앞자리 0 소실 가능), 문자열 `"0"` 은 유효, 수식 셀은 값으로 추론하지 않고 오류 | UX §4/운영 §4 “앞자리 0 복원 약속 금지” | `imports.py` | `test_imports.py` |
| I11 | 백업 첨부는 기본 **실제 복사**(hard link 는 `BACKUP_HARDLINK_ATTACHMENTS=true` 로만) | hard link 는 원본이 제자리 손상되면 백업도 손상 — 복원 테스트가 발견 | `backups.py`, `config.py` | `test_backups.py` |
| I12 | `pre_restore` 백업은 손상/누락 첨부를 `incompleteAttachments` 로 기록하고 계속 | 손상 첨부를 고치는 수단이 복원인데 복원 전 백업 실패가 복원을 막는 교착 | `backups.py` | `test_backups.py` |
| I13 | 복원 후 `backup_runs` 를 **백업 폴더의 manifest 로 재구성**, `restoreGeneration` 증가 | 복원된 DB 가 과거 이력을 가져와 복원 직전 백업이 목록에서 사라지고 폴더가 고아가 됨. 세대는 오래된 브라우저 초안 판별용 | `backups.py`, `/app-info` | `test_backups.py` |
| I14 | `frontend/dist` 는 Git 에 넣지 않고 `scripts/package.ps1` 로 zip 배포. zip 에는 `data/`·`config.json` 이 **없음**(덮어 풀어도 데이터 보존) | 빌드 산출물/사용자 데이터를 저장소에 섞지 않음 | `.gitignore`, `package.ps1` | zip 내용 검사 |
| I15 | 환경: Python/Node 는 conda-forge 로 설치(약관 미동의 채널 회피). 운영 의존성은 정확한 버전으로 `requirements.txt` 고정(ASCII 헤더) | 한글 주석이 cp949 로 읽혀 `alembic.ini` 파싱 실패 재현 | `requirements*.txt`, `alembic.ini` | 새 venv 에 설치 후 기동 |
| I16 | `colorama` 를 런타임 요구에 명시 | Windows 콘솔 색상용이며 click 메타데이터에 선언이 없어 자동 추적에서 빠짐 | `gen_requirements.py` | venv 기동 |
| I17 | 같은 날짜의 다른 담당자 일지는 **읽기 전용 목록**으로 노출 | “여러 담당자가 독립 작성”을 서로 확인할 수단. 수정/덮어쓰기는 불가 | `LogPage.tsx` | 브라우저 |
| I18 | 화면 구조: **업무일지 / To-Do / Issue 는 각각 최상위 탭**(프로젝트 선택 후 기록), **프로젝트 탭은 기준정보 전용**(목록·생성·상세·마일스톤·KPI). 주소 #/logs/<id>, #/todos/<id>, #/issues/<id>, #/projects/<id>; 예전 #/projects/<id>/log 등은 자동 이동 | 사용자 요청: 프로젝트 생성 직후 일지로 이동하던 흐름이 기준정보와 기록을 섞음 | App.tsx, WorkspacePage.tsx, ProjectsPage.tsx, UX §6 | 브라우저에서 탭/주소/이동 확인 |
| I19 | index.html 은 Cache-Control: no-cache로 제공 | 업데이트 후 브라우저가 옛 번들을 계속 쓰는 현상을 직접 겪음 | main.py | 브라우저 |
| I20 | 프로젝트 기준정보(기본 정보·배경/목적·마일스톤 행)는 **자동 저장하지 않고 명시적 ‘저장’ 버튼**으로만 반영(변경 표시, 되돌리기, 날짜 오류 시 저장 차단). 간트 막대 이동만 직접 조작이라 즉시 저장 | 사용자 지적: 저장 버튼이 없어 저장 여부를 알 수 없음 | ProjectInfo.tsx | 브라우저 |
| I21 | **프로젝트 복사는 프로젝트 목록 행의 ‘복사’ 버튼과 ‘새 프로젝트’ 창의 ‘복사할 기존 프로젝트’ 선택**에서만 제공(상세 화면에서 제거). 복사 후 팀·대표·단발성·기간은 창의 값으로 보정. 일지·트래커·실적·첨부·이력·기간은 복사하지 않음 | 사용자 요청 | ProjectsPage.tsx | 브라우저 |
| I22 | **업무일지 탭은 조회로 시작**: 왼쪽 달력(필터 기준 날짜별 건수) + 오른쪽 선택한 날의 일지 목록(프로젝트 횡단). 작성은 ‘업무일지 작성’에서 프로젝트(드롭박스+필터)·날짜를 고른 뒤 작성 화면(#/logs/<프로젝트>/<날짜>)으로 이동. 내 일지만 ‘이어서 작성’, 남의 일지는 읽기 전용 ‘보기’ | 사용자 요청 | LogsHome.tsx, LogView.tsx, WorkspacePage.tsx(LogEditorPage), App.tsx, API GET /logs, GET /logs/calendar | 브라우저 + `test_log_search.py` |
| I23 | **프로젝트 선택기 공통화**: 프로젝트 드롭박스 옆에 필터(범위=내 프로젝트/전체, 담당 조직, 팀, 상태, 이름). 기본 범위는 상단에서 고른 작성자가 대표·참여자인 프로젝트이며 필터는 브라우저에 기억. 업무일지(조회 필터·작성 시작), To-Do, Issue 모두 사용 | 사용자 요청 | ProjectPicker.tsx, projectFilter.ts | projectFilter.test.ts, 브라우저 |
| I24 | 프로젝트의 **대표 담당자·참여자 후보는 선택한 담당 팀의 구성원**(팀 변경 시 팀 밖 대표는 비움). ‘다른 팀 구성원도 표시’ 체크로 예외 허용 | 사용자 지적: 팀을 골라도 대표 목록에 영향이 없음 | `teamUsers.ts`, `ProjectsPage.tsx`, `ProjectInfo.tsx` | `teamUsers.test.ts`, 브라우저 |
| I25 | **패치는 `배포.bat`(scripts/deploy.ps1)로만 반영**: 코드 폴더는 mirror, 사용자 데이터·설정·가상환경은 제외, DB 사전 복사, 서버 실행 중/비설치 폴더/동일 폴더 거부, `-DryRun` 지원. 데이터를 프로그램 폴더 밖(절대경로 `DATA_DIR`)에 두는 것을 권장 | 사용자 보고: 패치할 때마다 테스트 폴더의 조직·사용자·프로젝트가 사라짐(폴더 통째 교체로 `data\` 가 함께 교체됨) | `deploy.ps1`, `배포.bat` | 격리된 가짜 설치본에서 데이터·설정 해시 동일, 삭제된 파일 정리, 안전장치 4종 확인 |
| I26 | **TASK 이름(선택)** 추가: `log_tasks.title`(최대 200자, 공백만 있으면 없음). 요약(titlePreview)은 이름 > 본문 첫 줄. 목록에는 이름(굵게)+본문 요약, JSON export 에 `title` 포함. **Alembic `0002_task_title`**(nullable 컬럼 추가, 기존 데이터 보존) | 사용자 요청. 설계 D05(TASK 이름 필수 아님, 제목 preview 가능)와 일치 | `models.py`, `schemas.py`, `services/logs.py`, `exports.py`, `0002_task_title.py`, `TaskCard.tsx` 등. **migration 필요** | `test_migrations.py`(0001 데이터 보존), `test_task_title.py`, 옛(0001) 백업 복원 후 자동 상향 테스트, 브라우저 |
| I27 | **필터는 ‘필터 적용’ 버튼(또는 이름 검색 Enter)을 눌러야 반영**. 입력 중에는 ‘조건이 바뀌었습니다’ 안내만 표시, ‘초기화’는 즉시 적용. 업무일지 조회·작성 시작·To-Do·Issue·프로젝트 목록·사용자 목록·To-Do/Issue 목록에 공통 적용. 단, 작성 시작/To-Do/Issue 의 ‘프로젝트 고르기’는 선택 동작이라 즉시 반영 | 사용자 요청(명시적 갱신) | `ProjectPicker.tsx`(`useDraft`, `ApplyButtons`), `ProjectsPage.tsx`, `MastersPage.tsx`, `TrackerPage.tsx` | `useDraft.test.tsx`, 브라우저(요청 0건 → 적용 시 조회) |
| I28 | **에디터 교체 시 파괴된 에디터 접근 금지** + 최상위 `ErrorBoundary`. 배경/목적 저장 후 목록 재로드로 `docKey` 가 바뀔 때 이미 destroy 된 Tiptap 에디터의 `commands` 에 접근해 앱 전체가 빈 화면이 되던 결함 수정. 저장 변경 여부는 ‘입력 이벤트’가 아니라 ‘저장본과 실제로 다른지’로 판단 | 사용자 보고(저장 시 화면 요소가 사라짐). 재현: `TypeError: Cannot read properties of null (reading 'commands')` | `RichEditor.tsx`, `ProjectInfo.tsx`, `ErrorBoundary.tsx` | `RichEditor.test.tsx`(수정 전 실패 확인), `ErrorBoundary.test.tsx`, 브라우저 3회 반복 저장 |
| I29 | **운영 탭의 JSON 사본 화면 개선**: 서버가 쓰는 json 폴더 절대경로, 대상별(업무일지·프로젝트·To-Do/Issue·조직/사용자) 프로젝트명·날짜·파일 상대경로·완료/대기/실패·마지막 갱신 시각 표시. `GET /exports/status` 에 `jsonDir`, `dailyCount`, 항목별 `projectName`, `relativePath`, `updatedAt` 추가 | 사용자 질문: 작성한 일지가 JSON으로 안 만들어진다고 느낌(실제로는 `테스트실행.bat` 이 쓰는 `data_test\json` 에 생성되어 있었음) | `exports.py`, `OpsPage.tsx` | `test_exports.py`(경로가 실제 파일과 일치), 브라우저 |
| I30 | **조직+사용자 한 파일(xlsx) 가져오기**: 시트 `조직`·`사용자`(+`작성 안내`). 구분·상위 코드·사용 여부·**팀 코드(조직 시트의 코드 목록)** 는 드롭박스, 사용자 시트의 `팀 이름(자동)` 은 수식(가져오기에서 읽지 않음). 같은 파일에서 새로 만드는 팀도 사용자가 코드/경로로 참조 가능. 조직 먼저 적용 → 새 팀 ID 로 사용자 연결, **한 트랜잭션(전량 적용/전량 중단)**. 팀 코드 드롭박스는 ‘경고’ 수준이라 이미 등록된 팀 코드도 입력 가능. 기존 단일 시트 양식·CSV 도 유지 | 사용자 요청(드롭박스, 조직 입력 내용을 사용자 입력에 재사용) | `imports.py`, `routes.py`(template `entity=workbook`), `MastersPage.tsx`. 빈 행 판단은 인식하는 열만 봄(수식 열 때문에 유령 500행이 생기던 위험 방지). migration 없음 | `test_import_workbook.py`(11), 변이 확인, **실제 Excel COM 으로 드롭박스·자동 팀 이름 확인**, 브라우저 end-to-end |
| I31 | **보고자료(PPT) 생성 탭**: `weekly-report` 의 `weekly_report` 패키지를 `backend/weekly_report/` 로 가져와 서버에서 실행(변경점은 `VENDORED.md`). 종류 = 주간 보고(ISO 주차, 기준 일자로 고름) / 기간 보고(시작일~마감일, ‘선택한 프로젝트 기간으로’) / 월간 종합(목요일 기준 그 달 주차). 주간·기간은 **주간업무 양식 ↔ 경영진 1장 요약 양식**을 고를 수 있음. 담당 조직·팀·상태·이름 필터 후 여러 프로젝트를 골라 **한 PPT 파일**로 만든다(과제 순서대로, 주간업무 양식은 과제당 1~2장). 입력은 JSON 사본 폴더가 아니라 **DB에서 바로 만든 export 형식**(사본은 늦을 수 있음). 기간 정리 결과는 `workspace/periods/<기간>` 에 따로 두어 주간 누적 요약 흐름과 섞지 않음 | 사용자 요청(보고자료 탭, 팀·담당 단위 선택, 주차 선택, 프로젝트 시작~마감 기간, a·b 양식 둘 다) | `services/reports.py`, `api/reports.py`, `ReportsPage.tsx`, `reportDates.ts`, `report_assets/`(템플릿·프롬프트·스키마·설정), `requirements.txt`(python-pptx·jsonschema·fonttools). DB 스키마 변경 없음 | `test_reports.py`(8), `reportDates.test.ts`, 원본 테스트 85개를 가져온 패키지로 재실행(통과), PowerPoint 로 연 슬라이드 이미지 확인, 브라우저 end-to-end |
| I32 | **AI 연결은 서버 설정 하나**: `config.json` 의 `ai_api_url`·`ai_api_key`(·`ai_model`·`ai_timeout_seconds`)가 있으면 서버가 직접 호출(live, 모든 사용자 공통), 없으면 **붙여넣기 방식**(작업이 ‘AI 응답 필요’로 멈추고 화면에서 프롬프트 복사 → 응답 붙여넣기 → 이어서 진행). 받은 응답은 **프롬프트 해시와 함께 저장**해 같은 입력이면 다시 묻지 않고, 업무일지가 바뀌면(프롬프트가 달라지면) 예전 응답을 쓰지 않음. ‘AI 정리 새로 받기’로 강제 갱신. 키는 화면·API 응답에 노출하지 않음. 붙여넣기 방식에서는 분량 줄이기(fit_to_budget)를 묻지 않고 원문 유지 + (계속) 장 | 사용자 결정(“API 연결은 직접, 서버에서 설정하면 모두 사용”). 사내 API 계약 미확인 | `config.py`, `weekly_report/ai.py`, `services/reports.py`(ServiceClient) | `test_reports.py`(재사용·변경 감지·새로 받기, 키 비노출). **실제 사내 API 연결은 미검증**(요청 형식은 원본과 같은 Chat Completions 가정) |
| I33 | **표·간트를 PPT 에 넣기(참고 슬라이드)**: 업무일지 본문의 표(병합 칸 유지, 길면 머리글 반복하며 다음 장)와 간트(진행률 포함), 프로젝트 마일스톤 일정(계획 막대=상태색, Baseline, 실적◆, 보고 기준일 점선)을 **그림이 아닌 PowerPoint 표·도형**으로 그려 각 과제 슬라이드 뒤에 넣음(받은 사람이 고칠 수 있게). 과제당 업무일지 표·간트 최대 15개. AI 입력에도 표는 “\| 칸 \| 칸 \|” 행, 간트는 “[간트] 이름 (기간, 진행률)” 로 들어감 | 사용자 질문(2-1) | `services/report_slides.py`, `weekly_report/worklog.py` | `test_reports.py`(병합·쪽 나눔·머리글 반복·쪽 번호), PowerPoint 렌더 이미지 |
| I34 | **보고자료 작업 상태는 파일**(`data/reports/jobs/*.json`)로 두고 서버 안 작업 스레드 하나가 순서대로 처리(작업공간이 하나라 직렬). 서버가 도중에 꺼지면 다음 시작 때 다시 대기열로. 결과는 `data/reports/output/<작업>/`, 최근 200개 보관. 생성물이라 DB·migration 을 늘리지 않음. **백업(DB·첨부)에는 포함되지 않음** — 받아 둔 AI 응답·누적 요약 흐름이 디스크 고장 시 사라질 수 있음(다시 만들 수 있음) | 설계 판단 | `services/reports.py`(JobStore), `main.py`(작업 스레드) | `test_reports.py`(중단 후 재대기, 파일 경로 제한) |
| I35 | **초기 설정 실행 파일 `초기설정.bat`**(`scripts/setup-env.ps1`): 실행기와 같은 순서 **Conda → embedded → venv** 로 시도해 먼저 *모든 런타임 패키지를 가져올 수 있게 된* 하나에서 멈춘다. Conda 는 `worklog` env 가 없으면 conda-forge 로 생성(Python 3.12, `-Dev` 면 Node.js 22), 있으면 패키지만 설치. embedded 는 `runtime\python` 이 있을 때만(`._pth` 의 `import site` 활성화·원본 보관, pip 없으면 wheels 의 pip 또는 get-pip.py). venv 는 PC 의 Python 3.11+(py, PATH, conda base 순; conda base 는 venv 생성에만 쓰고 설치하지 않음). `wheels` 폴더가 있으면 자동 오프라인. 끝에 실행기가 실제로 고를 환경을 표시. 실행기는 사용자 폴더 `%USERPROFILE%\.conda\envs\<이름>` 의 env 도 찾도록 보강(설치 폴더에 쓰기 권한이 없으면 conda 가 env 를 거기 만듦) | 사용자 요청 | `초기설정.bat`, `scripts/setup-env.ps1`, `select-python.ps1`, `setup-venv.ps1`(보고자료 패키지 확인), `make-wheelhouse.ps1`(pip wheel 포함), `package.ps1`, `실행.bat`(안내 문구) | `test_setup_env.py`(6), 실제 실행: 기존 Conda env, **새 Conda env 생성(시험 이름, 확인 후 삭제)**, 새 venv(Python 3.13). embedded 실제 설치는 미실시 |
| I36 | **보고자료 팀장 요약 페이지**: 주간·기간 보고 + 주간업무 양식에서 ‘팀장 요약 페이지 포함’(화면 기본 켜짐, API 기본 끔)을 켜면 선택 과제를 팀(`team.name`)으로 묶어 **팀별 [요약 n장 → 그 팀 과제 장표·참고 슬라이드]** 순서로 한 PPT를 만든다(팀 순서 = 선택 목록에 처음 나온 순서, 과제 번호 (n/N)은 팀 안에서). 요약 문장은 과제마다 AI(`project_summary`)가 배경·진행·이슈·잘한점·계획으로 쓰고, 순서·파랑(1414FE, 그 주/기간 업무일지가 근거인 문장)·글자 크기(11→10.5→10pt, 넘치면 과제 단위로 다음 장 "(1/2)")·수치/날짜 근거 검증은 룰. 형식은 템플릿 0번 양식·1번 실제 작성본(굵은 `n. 과제명`, `- 문장.(M/D)`, `  . 세부`, 카테고리 이름 표시 없음). 제목 `1. {팀} (n/N)`. 작성자는 화면 입력(‘작성자(팀장)’, DB에 팀장 개념이 없어서), 비우면 첫 과제 담당자. 템플릿은 4장(0 요약, 1 작성본 참고, 2 주간, 3 예시)으로 바꾸고 장 역할은 도형 이름으로 판별(참고 장은 출력 안 함) | 사용자 요청(주간업무 팀장 요약본), 사용자 결정(팀별 배치·화면 입력 작성자·주간+기간·기본 켜짐) | `services/reports.py`(`_weekly_template`·`_team_summary`), `schemas.py`, `weekly_report/summary.py`·`team.py`·`ppt/render.py`(원본에서 가져옴, `VENDORED.md`), `report_assets/`(프롬프트 v0.7·스키마·4장 템플릿), `ReportsPage.tsx`. DB 스키마 변경 없음 | `backend/tests/test_reports_team.py`(4: 2팀 배치·작성자·파랑, 끔=기존 결과, 기간 응답 키, 경영진 양식 무시), `test_team_summary.py`(3), tsc·vitest 45, LibreOffice 렌더 이미지. 실제 EXAONE 응답 품질은 미검증 |
| I37 | **상단 탭 → 왼쪽 세로 트리 내비게이션**(I18의 상단 탭 구조 대체): Windows 탐색기 왼쪽 창처럼 접고 펴는 트리 `담당 ▸ 팀 ▸ PJT ▸ Worklog(▸ To-Do, Issue) / 자료 생성기(▸ 주간업무자료, 경영진보고자료)`. 오른쪽 화면은 기존 화면·주소를 그대로 씀: PJT=프로젝트 정보 `#/projects/<id>`, Worklog=그 과제 달력+목록 `#/logs?project=<id>`(과제 필터만 적용, 위에 [업무일지 | To-Do | Issue] 탭 줄), To-Do/Issue `#/todos|issues/<id>`, 자료 생성기 `#/reports?project=<id>[&template=weekly|exec]`(그 과제 미리 선택, 다른 과제 추가 가능). **완료 과제 = 일반·수시 업무를 뺀 마일스톤이 모두 완료·취소이고 1개 이상 완료, 또는 프로젝트 상태 완료 → 검회색(#6b7076)+‘완료’ 표시, 진행 중 → 검정**, 팀 안에서는 진행 중 과제 먼저. 트리 위 검색·‘내 프로젝트만’, 펼침 상태는 브라우저에 저장, 지금 주소의 경로는 자동으로 펼침. 트리 아래 ‘전체 보기·관리’ 묶음(전체 업무일지·To-Do·Issue, 보고자료(여러 과제·팀장 요약), 프로젝트 목록, 조직·사용자, 운영). 좁은 화면(≤860px)은 ☰ 서랍 | 사용자 요청(흐름이 보이게 담당→팀→PJT 계층, 완료 과제 회색), 사용자 결정(Worklog 안에 To-Do·Issue, PJT 클릭=프로젝트 정보, 자료 생성기는 PJT에만, 마일스톤 기준 완료) | `App.tsx`(상단 탭 제거·shell), `features/SideNav.tsx`·`navTree.ts`·`ProjectWorkBar.tsx`, `LogsHome`(projectId), `ReportsPage`(initialProjectIds·initialTemplate), `app.css`, 백엔드 `services/projects.py`(`milestoneSummary`, 페이지당 집계 쿼리 1번). DB 스키마 변경 없음 | `navTree.test.ts`(13), `SideNav.test.tsx`(4), `backend/tests/test_project_summary_list.py`, Chromium 화면 확인(넓은 화면·좁은 화면 서랍) |

### 이후 변경 기록
- 2026-10-04 / I01~I17 / 위 표의 이유 / 위 표의 근거 / 위 표의 영향 / 위 표의 검증. 확정 요구 D01~D31 은 변경하지 않았다. Migration: `0001_initial_schema` 하나(신규 설치 기준, 기존 데이터 없음).
