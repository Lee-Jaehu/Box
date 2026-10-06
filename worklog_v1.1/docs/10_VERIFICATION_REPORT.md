# Worklog 구현·검증 보고서

작성: 2026-10-04 (Asia/Seoul) · 환경: Windows 11 Enterprise 10.0.26100 x64, 개발 PC 1대(운영 PC 아님)

이 문서는 **실제로 실행해서 확인한 것**과 **확인하지 못한 것**을 구분해 적는다. “확인함”은 아래 명령/절차로 재현 가능한 경우만 쓴다.

## 1. 개발 환경과 고정 버전

| 항목 | 값 | 비고 |
|---|---|---|
| Python | 3.12.14 (conda-forge) | 서버 최소 요구는 3.11 (`select-python.ps1` 프로브) |
| SQLite (런타임) | 3.53.4 | `sqlite3.sqlite_version` |
| Node.js / npm | 22.23.2 / 10.9.8 | 개발 빌드 전용. 운영 PC 불필요 |
| Conda | 26.1.1 (`C:\ProgramData\miniconda3`) | env `worklog` 는 **conda-forge** 로 생성 |
| 서버 | FastAPI 0.142.2, Starlette 1.7.0, Uvicorn 0.54.0, SQLAlchemy 2.1.3, Alembic 1.20.0, Pydantic 2.13.5, openpyxl 3.1.5, Pillow 12.3.0, python-multipart 0.0.32 | 전이 포함 정확한 버전: `backend/requirements.txt` |
| 화면 | React 19.3.0, TypeScript 7.0.2, Vite 8.3.2, Tiptap 3.31.4 (core/starter-kit/table/task-list/task-item/react), Frappe Gantt 1.2.2 | `frontend/package.json` (정확 고정), `package-lock.json` |
| 테스트 도구 | pytest 9.1.1, httpx 0.28.1, vitest 5.0.3, jsdom 30.1.1 | |

- Anaconda 기본 채널(`repo.anaconda.com/pkgs/main`)은 이용약관 동의를 요구하므로 **동의를 대신하지 않고** conda-forge 로 환경을 만들었다:
  `conda create -n worklog --override-channels -c conda-forge python=3.12 nodejs=22`
- 라이선스: 운영 의존성 전부 MIT/BSD/Apache-2.0/PSF/MIT-CMU/ISC 로 선언됨(`THIRD_PARTY_NOTICES.md`). 선언값을 옮긴 것이며 법무 검토는 하지 않았다.

## 2. P0 편집 시제품 — 라이브러리 검증 결과

### Tiptap 3.31.4
| 항목 | 결과 | 근거 |
|---|---|---|
| 문서 JSON 왕복(문단·굵게·링크·체크리스트·표(colspan/rowspan)·간트·이미지) | **확인함** | `roundtrip.test.ts` (jsdom), 브라우저에서 직렬화→JSON→다시 열기 후 재직렬화 바이트 동일(5238자) |
| 두 번째 왕복에서 구조 불변(idempotent) | 확인함 | 같은 테스트 |
| 알 수 없는 node/mark/위험 링크를 **조용히 삭제하지 않고** 위치와 함께 오류 | 확인함 | 서버 `documents.py` + `test_logs.py::test_unknown_node...`, 프런트 `validateDocument` |
| 체크리스트 토글, 표 삽입·행열 추가/삭제 명령 | 확인함 | `commands.test.ts`, 브라우저 버튼 클릭 |
| 셀 병합 `colspan/rowspan` **저장·복원** | 확인함 | 왕복 테스트 (병합 **조작**의 마우스 UI 는 §7 미실시) |
| Excel 유사 HTML 표(`mso-*` 스타일 포함) → 행/열/셀 텍스트 보존 | 확인함(합성 HTML) | `commands.test.ts`. 서식(색·테두리·수식)은 보존하지 않음. 실제 Excel 클립보드 붙여넣기는 §7 미실시 |
| 간트/이미지 custom node 속성 왕복 | 확인함 | `attachmentUseId`, `items[]`, `displayRange` 보존 |
| 간트 선택 상태에서 표/이미지 삽입 시 **간트가 사라지는 결함** | **발견·수정** | atom node 가 선택된 채 `insertContent`/`insertTable` 하면 선택 node 가 대체됨. `leaveNodeSelection` 으로 해결, 회귀 테스트 포함 |

### Frappe Gantt 1.2.2
| 항목 | 결과 |
|---|---|
| 한글 라벨/월 헤더(`language: 'ko'`) 렌더링 | 확인함 (브라우저) |
| 날짜 의미 | 입력 `end`가 자정이면 내부에서 +24h(포함 종료). 날짜 변경 콜백의 `end`는 (배타 종료 − 1초). **저장 계약은 “포함 종료일, 로컬 달력 날짜”로 통일**하고 `gantt/adapter.ts` 에서 변환. 타임존 변환(UTC) 사용 금지 |
| 막대 이동 → 날짜 | 10/04~10/06 을 2일 이동 → 10/06~10/08 (길이 3일 유지) — 확인함 (브라우저, 합성 마우스 이벤트) |
| 오른쪽 핸들로 기간 조절 | 10/06~10/08 → 10/06~10/09 — 확인함 (브라우저, 합성 마우스 이벤트) |
| 하루짜리/월 경계/타임존 | 단위 테스트(`adapter.test.ts`) |
| 패키지 `exports` 가 CSS 서브패스를 열지 않음 | `dist/frappe-gantt.css` 를 `frontend/src/vendor/` 로 복사(MIT 고지 포함) |

> 자동화 도구의 `left_click_drag` 는 SVG 막대를 움직이지 못했다. Frappe 가 SVG 의 `offsetX` 이벤트를 쓰기 때문에, 같은 이벤트를 SVG 에 직접 발생시켜 검증했다. **실제 사람의 마우스 드래그는 미실시**(§7).

### 이미지
- 업로드 시점은 설명 없이 성공, **정식 저장 시점에 설명 필수 검증**(필드 오류 `tasks[i].attachments[j].description`) — 서버 테스트 + 브라우저 확인.
- 같은 바이너리를 두 TASK 에서 쓰면 사용처(`task_attachments`)별로 다른 설명 — 테스트 확인.

## 3. 자동 테스트

| 영역 | 파일 | 테스트 수 |
|---|---|---|
| 일지 unique/revision/동시성/휴지통/문서 검증/snapshot | `test_logs.py` | 11 |
| 멱등성(같은 key·다른 payload·clientEntryId·ref 누락) | `test_idempotency.py` | 7 |
| tracker 완료+TASK 원자성(fault injection)·상태 규칙 | `test_trackers.py` | 15 |
| 성과 계산(before=0, %p, 부호, 단위/기간 불일치) | `test_achievements.py` | 9 |
| JSON export(재시작·수정 race·교체 실패·빈 날짜·삭제 프로젝트·재생성) | `test_exports.py` | 9 |
| 첨부(이미지 설명 필수·20MB 경계·MIME·경로) | `test_attachments.py` | 12 |
| 명단 가져오기(전량 차단·모호·사번 0·stale·수식) | `test_imports.py` | 10 |
| 백업/복원(manifest·14개·실패 보존·복원 일치·세대) | `test_backups.py` | 9 |
| P1 기준정보/프로젝트/마일스톤/기준 일정 | `test_masters_projects.py` | 12 |
| 휴지통 | `test_trash.py` | 5 |
| 20명 동시 저장 정합성 + 쓰기 mutex 해제 | `test_concurrency.py` | 2 |
| Windows 실행기(Conda→embedded→venv, 한글·공백 경로, 앱 오류 후 재시작 없음) | `test_launcher.py` | 7 |
| 기동 스모크 | `test_smoke.py` | 1 |
| **백엔드 합계** | | **109 — 전부 통과** |
| 프런트: 간트 어댑터 6, 문서 왕복 6, 에디터 명령 4, 초안 로직 8 | `vitest` | **24 — 전부 통과** |

재현:
```bash
python -m pytest              # 백엔드 109 (Windows 에서 약 2분)
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

### 테스트가 실제로 결함을 잡는지 (변이 확인)
핵심 보호 로직을 일부러 깨뜨려 대응 테스트가 실패하는지 확인했다(모두 실패 확인 후 원복):
revision 검사 제거 → `test_stale_revision...` 실패 / export 완료 표시를 최신 revision 으로 변경 → `test_export_does_not_overwrite_newer...` 실패 / import 오류 차단 제거 → `test_any_error_blocks...` 실패 / 이미지 설명 검사 제거 → `test_upload_does_not_require...` 실패 / 완료 중간 fault 제거 → fault 롤백 테스트 실패 / `BEGIN IMMEDIATE` 제거 → 동시성 테스트 2개 실패.

### 테스트가 잡아낸 실제 결함 (수정 완료)
1. 간트 선택 상태에서 표/이미지 삽입 시 간트 삭제 (§2).
2. **백업이 첨부를 hard link 로 묶음** → 원본이 제자리에서 손상되면 백업도 손상. 기본을 실제 복사로 변경(`BACKUP_HARDLINK_ATTACHMENTS` 옵션만 남김).
3. **라이브 첨부가 손상되면 복원 전 백업이 실패해 복원 자체가 막히는 교착** → `pre_restore` 백업만 손상 파일을 `incompleteAttachments` 에 기록하고 계속(일반 백업은 계속 엄격하게 실패).
4. **복원하면 `backup_runs` 이력도 과거로 돌아가 복원 직전 백업이 목록에서 사라지고 폴더가 고아가 됨** → 복원 후 백업 폴더 manifest 로 이력 재구성(`reindex_backups`).
5. 에디터가 마운트 시 내용이 같은 `onUpdate` 를 내보내 “변경됨”으로 표시 → 같은 내용은 변경으로 보지 않음.
6. 브라우저 UTC 날짜(`toISOString`) 사용으로 자정 전후 하루 어긋남 → 로컬 날짜 헬퍼.

## 4. 실제 서버에서의 확인 (브라우저·프로세스)

| 시나리오 | 결과 |
|---|---|
| `실행.bat` 실제 실행 | Conda `worklog` 선택, UTF-8 한글 안내 출력, `/api/v1/health` 200, 빌드된 화면 `/` 200 (임시 data 폴더 사용) |
| 운영 구성(개발 도구 없는 `.venv` + 고정 requirements)에서 기동 | `setup-venv.ps1` 설치 → 서버 기동·health 200, 런처가 `.venv` 로 폴백 |
| 화면: 사용자 선택 → 프로젝트 → 일지 작성(한글·표·이미지·설명) → 저장 → **새로고침 후 서버본에서 복원** | 확인함 (텍스트, 표, 이미지 로딩, 설명 모두 복원) |
| 저장 전 새로고침 | 브라우저 임시저장 초안 복구 배너 + 서버는 이전 revision 유지 |
| 다른 곳에서 먼저 수정 후 저장 | 충돌 배너, **내 입력 유지**, 자동 병합/덮어쓰기 없음, “최신본 기준으로 다시 편집(내 초안 보관)” 동작 |
| To-Do “완료 + 오늘 한 일에 남기기” | tracker 완료, 이벤트, 일지 TASK 추가, 일지 revision 증가가 한 번에 반영 |
| 백업·JSON | 첫 저장 직후 일일 자동 백업 자동 실행, 수동 백업, `daily.json`(sourceRevision 3, TASK 2, 첨부 1) DB 와 일치 |
| **프로세스 강제 종료**(`scripts/kill_restart_check.py`) | DB 저장 직후 `TerminateProcess` → 재시작 후 일지 정상, 대기 중이던 export 가 재개되어 `daily.json` 생성, pending/failed 0 |
| 패키지(`scripts/package.ps1`) | zip 59개 항목, `data/`·`config.json`·`.venv`·`node_modules`·`tests`·`*.sqlite3` 미포함, 한글 파일명 `실행.bat` UTF-8 보존 |

## 5. 약 20명 부하 확인 (`scripts/loadtest.py`)

20 스레드가 각자 일지 저장·수정·조회, To-Do 등록, 완료+TASK 추가를 수행하고 마지막에 유실/중복을 검증한다. **이 개발 PC에서 측정한 값이며 운영 PC 성능을 보장하지 않는다.**

| 시나리오 | 저장 p50 | 저장 p95 | 저장 max | 오류·유실·중복 |
|---|---|---|---|---|
| 사용자 생각 시간 0~3초(현실적) ×2회 | 0.03~0.04s | **0.06~0.15s** | 0.27s | 0 |
| 20명이 같은 순간 서로 다른 일지 저장(burst, 위 4회 실행 합산) | — | 0.66~1.11s | 1.13s | 0 |
| 쉬지 않고 연타(극단) ×2회 | 1.6~1.9s | **2.05~2.23s** | 2.3s | 0 |
| (참고) 쓰기 mutex 도입 **전** 극단 시나리오 | 0.23s | 4.4s | 6.0s | 0 |

- 극단 시나리오는 20명이 0초 간격으로 계속 저장하는 비현실적 부하라서 2초 목표를 **근소하게 넘는다**(목표는 “일반 텍스트/표 일지 혼합 p95 2초 이내”이고 현실적 시나리오는 충족). 저장 1회 약 40ms 는 Python/ORM CPU 비용이며 `synchronous=NORMAL` 로 바꿔도 빨라지지 않아(디스크 fsync 가 병목이 아님) **내구성 설정은 FULL 을 유지**했다.
- 같은 일지에 20명이 동시에 신규 저장: 정확히 1건 성공, 19건 명확한 409 (`LOG_EXISTS`).
- 원인 분석: SQLite busy handler 는 대기 순서가 없는 polling 이라 동시 쓰기에서 일부 요청이 수 초 굶었다. 프로세스 내 쓰기 mutex(공정 대기) + `BEGIN IMMEDIATE` 로 최악 지연을 절반 이하로 줄였다(`db.py`).
- 첨부 20MB 동시 업로드, 큰 표, 백업/export 와 저장의 동시 실행은 부하 시험에 **포함하지 않았다**(§7).

## 6. 환경에서 발견한 주의 사항

- Windows 는 일부 TCP 포트를 제외 범위로 예약한다(이 PC: 80, 4567-4568, **8003**, 8005, 61811-61813). 예약 포트에 바인드하면 `WinError 10013` 으로 서버가 종료된다(앱은 원인을 그대로 출력하고 재시작하지 않음). 기본 8000 은 이 PC 에서 사용 가능. 확인: `netsh interface ipv4 show excludedportrange protocol=tcp`. 필요하면 `config/config.json` 의 `PORT` 변경.
- `alembic.ini`/requirements 파일은 한글 Windows 시스템 코드페이지(cp949)로 읽히는 도구가 있어 **ASCII 로 유지**한다(한글 주석 시 `UnicodeDecodeError` 재현됨).
- PATH 에 Python/Node/Git 이 없을 수 있다. 런처는 PATH 에 의존하지 않고 후보 경로를 직접 탐색한다. 이 PC 에는 Git 이 없어 **저장소는 git 으로 관리되지 않는 상태**다.

## 7. 확인하지 못한 것 (완료로 표시하지 않음)

| 항목 | 상태 | 이유/영향 |
|---|---|---|
| **한글 IME 조합 중 입력·Enter·목록 종료** | **미실시** | 자동화 입력은 조합(composition) 이벤트를 발생시키지 않는다. 실제 IME 로 수동 확인 필요(§Windows smoke) |
| 실제 Excel/브라우저 클립보드 표 붙여넣기 | 미실시 | 합성 HTML 만 검증 |
| 표 열 너비 드래그, 셀 병합/분할의 **마우스 조작 UI** | 미실시 | 명령과 저장/복원은 확인 |
| 실제 사람의 간트 막대 드래그/리사이즈 | 미실시 | 합성 이벤트로 날짜 계산 경로만 확인 |
| embedded Python(`runtime/python`) 패키징 (`_pth`, site-packages, native wheel) | 미실시 | 선택 순서 로직만 테스트. embeddable 배포본은 만들지 않았다 |
| 다른 PC 에서 접속, Windows 방화벽, 절전·장시간 운영 | 미실시 | localhost 만 확인. 방화벽은 자동 변경하지 않는다 |
| 다른 브라우저(Chrome/Edge 정식), 모바일 | 미실시 | Claude 데스크톱 내장 브라우저(Chromium)에서만 확인. 화면 반응형은 CSS 만 |
| 접근성(스크린리더·키보드 전용) 감사 | 미실시 | aria 레이블 일부만 적용 |
| 20MB 파일 동시 업로드·백업 중 저장·큰 문서 부하 | 미실시 | |
| 한글/공백 설치 경로에서 **전체 앱** 실행 | 부분 | 런처 선택·앱 오류 처리는 한글+공백 경로에서 확인. 서버 전체 구동은 ASCII 경로에서만 |
| 라이선스 법무 검토, 보안 점검(침투) | 미실시 | 인증 없는 사내 도구 전제 |
| 300명 확장 | 범위 밖 | |

## 8. 보고자료(PPT) 연동 확인 (2026-10-04 추가)

확인함
- 가져온 패키지(`backend/weekly_report`)로 **원본 저장소 테스트 85개 통과·2개 건너뜀**(LibreOffice 미리보기). 이 재실행에서 기간 보고용 변경이 만든 결함 1건(응답 키 변수 `key` 가 함수 뒤쪽 반복문 변수와 겹쳐 검증 보고서 이름이 `validation_pinned_facts.txt` 가 됨)을 찾아 고쳤고, `test_reports.py` 에 회귀 확인을 넣었다.
- `tests/test_reports.py` 8개: 붙여넣기 흐름(틀린 단계 응답 422·저장 안 함 → 2단계 응답 → 완료), 같은 입력 응답 재사용 / 일지 수정 시 다시 묻기 / ‘새로 받기’, 서버 AI(가짜 응답)로 2개 과제 주간 덱·기간 경영진 요약·기간 주간 양식·월간 종합, 설정 API 에 키 비노출, 입력 검증(주차·기간 역전·366일 초과·월·없는 프로젝트·작성자 없음), 중단 작업 재대기·경로 탈출 차단, 표 쪽 나눔 머리글 반복, python-pptx 가 없는 환경에서도 서버가 뜨고 보고자료만 503 안내.
- **PowerPoint(이 PC 의 실제 PowerPoint, COM)** 로 생성 PPT 를 열어 슬라이드를 이미지로 내보내 확인: 주간업무 양식(과제 2개, (1/2)(2/2)), 마일스톤 일정 간트(상태색·Baseline·실적◆·기준일 점선), 업무일지 표(병합 칸 유지), 업무일지 간트(진행률), 경영진 1장 요약 + 참고 장 쪽 번호(2 / 2), 월간 종합. 이때 찾은 표시 문제 4건(참고 장에 마스터 쪽 번호 겹침, 기간 미입력 과제의 목표 일정이 보고 범위로 표시, 배경·목적 미입력이 “- -. -”, 간트 세로선의 테마 그림자)을 고친 뒤 다시 확인했다.
- 실제 서버(임시 데이터 폴더, 포트 18110) + 브라우저: 작성자 선택 → 팀 필터 적용 → 프로젝트 체크 → 주간 보고 생성 → ‘AI 응답 필요’ 에서 프롬프트 표시·복사, JSON 이 아닌 응답의 안내 문구, 설명 문장+```json 이 섞인 응답 저장 → 누적 요약 응답 → 완료(4장) → PPT·검사 보고서 내려받기(200, 올바른 Content-Type). 기간 보고 탭의 ‘선택한 프로젝트 기간으로’(9/1~10/4, 34일)와 경영진 양식 선택 → 기간 정리 프롬프트(‘지정한 기간’, 표 행) 확인. 서버 오류 로그 없음.

확인하지 못함
- **사내 EXAONE(또는 다른 사내 AI) API 실제 연결**: 요청 형식은 원본 그대로 Chat Completions 가정이며 계약 문서가 없다. 서버 AI 흐름은 가짜 응답으로만 시험했다.
- 실제 AI 가 쓴 문장의 품질·분량(경어체 40~60자 규칙 등)은 AI 에 달려 있다. 규칙 위반은 검사 보고서에 ‘주의’로 남고 PPT 생성은 막지 않는다.
- 다른 PC 의 PowerPoint·LG스마트체 미설치 PC 에서의 표시(글꼴은 PPT 에 넣지 않는다), 아주 많은 과제(30개)·긴 기간(1년)에서의 생성 시간.
- 운영 템플릿의 쪽 번호: 주간업무 템플릿은 `firstSlideNum=0`, 마스터 쪽 번호 “n / 140”(고정 글자)이라 첫 장이 0 으로 보인다. 회사 양식 그대로 두었다.

## 9. 초기 설정 실행 파일 (2026-10-04 추가)

확인함
- `tests/test_setup_env.py` 6개: 가짜 Conda 폴더로 순서 판단(기존 env → 패키지 설치 계획, env 없음 → conda-forge 생성 계획), Conda 없음 → embedded → venv 폴백, 전부 없음 → 이유를 순서대로 표시하고 실패 코드, `wheels` 폴더 자동 오프라인, 한글·공백 경로에서 `초기설정.bat` 실행. 기존 `test_launcher.py` 7개도 함께 통과.
- 이 PC 에서 실제 실행: ① 기존 Conda env `worklog` → 패키지 확인 후 완료, ② **새 Conda env 생성**(시험 이름 `worklog-setuptest`, conda-forge Python 3.12.14 → 패키지 설치 → 가져오기 확인, 확인 후 삭제), ③ 임시 폴더에 새 venv(conda base Python 3.13.12 로 생성, 고정 버전 패키지 모두 설치·가져오기 확인). 세 경우 모두 base 환경은 바꾸지 않았다.
- 주의: 이 PC 의 Conda 는 기본 채널 약관 동의가 안 된 상태라 `conda env remove` 가 거부되어 `conda remove --all --override-channels -c conda-forge` 로 지웠다. 설정 스크립트는 생성·설치 모두 conda-forge 만 쓴다.

확인하지 못함
- **embedded Python 경로의 실제 설치**(Windows embeddable 패키지 내려받기·`._pth` 수정·get-pip.py/pip wheel 설치). 계획 판단만 테스트했다.
- 오프라인(`wheels`) 실제 설치, 프록시 환경, 관리자 권한이 없는 PC 에서 `%USERPROFILE%\.conda\envs` 에 env 가 만들어지는 경우.
