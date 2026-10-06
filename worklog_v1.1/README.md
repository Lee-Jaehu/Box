# Worklog

개인 Windows PC 한 대에서 수동 실행하는 사내 업무일지 서비스. 프로젝트 → 마일스톤 → TASK 구조로 매일 한 일을 기록하고, SQLite 를 원본으로 두고 읽기 쉬운 JSON 사본을 자동 생성한다. MVP 동시 작성 목표는 약 20명이며 로그인/권한은 없다(작성자 선택은 자기신고).

- 설계 문서: [docs/README.md](docs/README.md) (결정 원장 [08](docs/08_DECISIONS.md), 개발 계획 [07](docs/07_DEVELOPMENT_PLAN.md))
- **구현·검증 결과와 미실시 항목: [docs/10_VERIFICATION_REPORT.md](docs/10_VERIFICATION_REPORT.md)**
- 운영 PC 스모크 체크리스트: [docs/11_WINDOWS_SMOKE.md](docs/11_WINDOWS_SMOKE.md)

## 현재 상태 (2026-10-04)

**구현·검증됨** (자동 테스트 백엔드 149 + 프런트 45 통과, 실제 서버/브라우저 확인 — 자세한 근거는 검증 보고서)

| 단계 | 내용 |
|---|---|
| P0 | Tiptap 문서 JSON 왕복(표 병합 속성·체크리스트·간트·이미지), 간트 날짜 계약, 이미지 설명 필수, 라이브러리 버전/라이선스 고정 |
| P1 | FastAPI + 빌드 화면 제공, SQLite(WAL)/Alembic, 조직·사용자(사번 선택), Excel/CSV 가져오기(전량 검증), 프로젝트·마일스톤·KPI, 일반·수시 업무 자동 생성, 공용 간트, 기준 일정 확정, `실행.bat` |
| P2 | 일지(프로젝트+작성자+날짜 고유, revision, Idempotency-Key), 여러 TASK/마일스톤, IndexedDB 초안·복구·충돌 처리, 정량/정성 성과·KPI snapshot, 이미지/문서 첨부 |
| P3 | To-Do/Issue, 완료/해결 + 선택 TASK 생성(원자적), 재개, Issue→대응 To-Do, 휴지통/복원 |
| P4 | 내구성 있는 JSON export 작업, 재생성, bundle, SQLite 백업(최근 성공 14개)·manifest·복원, 강제 종료 후 재개 |
| P5(일부) | 약 20명 혼합 부하 스크립트와 측정(이 PC), 동시 저장 정합성 테스트 |
| 추가 | **보고자료(PPT) 탭**: 주간 보고(주차) / 기간 보고(시작일~마감일) / 월간 종합, 주간업무 양식 ↔ 경영진 1장 요약 양식, 담당 조직·팀 필터로 여러 프로젝트를 한 PPT 로, 업무일지 표·간트·마일스톤 일정을 PPT 표·도형으로 넣기 (결정 I31~I34), **팀장 요약 페이지**(팀별 맨 앞, AI 요약, 결정 I36) |

**미실시/제한** — 한글 IME 실제 조합, Excel 실제 클립보드 붙여넣기, 표/간트 마우스 UI 의 실제 사람 조작, embedded Python 패키징, 다른 PC 접속·방화벽, Chrome/Edge 정식 브라우저 검증, 접근성 감사, 운영 PC 성능. 이 항목은 **완료로 표시하지 않았다** (보고서 §7). 극단적 연타 부하에서 저장 p95 가 2초 목표를 근소하게 넘는다(현실적 부하는 충족, 보고서 §5).

**범위 밖(구현하지 않음)**: 300명 확장, 인증/SSO.
보고자료의 AI 정리는 **관리자가 서버에 설정한 AI 주소**(사내 EXAONE 등)로만 보내거나, 설정이 없으면 사용자가 프롬프트를 직접 복사해 AI 에 붙여넣는 방식이다. 어떤 AI 로 업무 내용을 보낼지는 운영자가 정한다. 사내 AI API 실제 연결은 아직 검증하지 않았다.

## 보고자료(PPT)

1. 상단 **보고자료** 탭 → 종류(주간 보고 / 기간 보고 / 월간 종합)와 날짜를 고른다. 주간 보고는 기준 일자가 속한 ISO 주(월~일), 기간 보고는 시작일~마감일(‘선택한 프로젝트 기간으로’ 버튼), 월간 종합은 목요일이 그 달에 있는 주들.
2. 양식(주간업무 양식 / 경영진 1장 요약 양식), 담당 조직·팀·상태 필터 → **필터 적용** → 프로젝트를 체크(여러 개 가능, 최대 30).
3. 주간·기간 보고 + 주간업무 양식이면 **팀장 요약 페이지 포함**(기본 켜짐)과 작성자(팀장)를 정한다. 켜면 팀별로 [팀장 요약 1장 → 그 팀 과제 장표] 순서가 된다.
   요약 페이지는 템플릿 0번 양식·1번 작성본 형식(굵은 `n. 과제명`, `- 문장.(M/D)`, `  . 세부`)이고, 이번 주(기간) 업무일지가 근거인 문장만 파란색이다. AI 응답은 과제마다 1번 더 필요하다(결정 I36).
4. 참고 슬라이드(업무일지 표·간트, 마일스톤 일정)를 고르고 **PPT 만들기**. 다른 화면으로 가도 서버에서 계속 만든다.
5. AI 연결이 없으면 ‘AI 응답 필요’가 나온다 → **프롬프트 복사** → 사내 AI 에 보내기 → 받은 JSON 붙여넣기 → **응답 저장 후 계속**(과제마다 2~3번, 팀장 요약을 켜면 1번 더). 같은 입력이면 다음부터는 다시 묻지 않는다.
6. 완료되면 PPT 와 검사 보고서(숫자·날짜 근거 확인, PPT 재검사)를 내려받는다. **최근 보고자료** 목록은 모든 사용자에게 보인다.

서버 AI 연결: `config\config.json` 에 `AI_API_URL`, `AI_API_KEY`(필요 시 `AI_MODEL`, `AI_TIMEOUT_SECONDS`)를 넣고 서버를 다시 시작한다. 요청은 OpenAI 호환 Chat Completions 형식(`messages`, `response_format=json_object`, `Authorization: Bearer <키>`)으로 보낸다. 사내 API 형식이 다르면 `backend/weekly_report/ai.py` 의 `ChatCompletionsAdapter` 를 바꾼다. 결과·받은 AI 응답은 `DATA_DIR\reports\` 에 있으며 **DB 백업에는 포함되지 않는다**.

## 빠른 시작

### 개발 PC (Node.js 필요: 화면 빌드 전용)

```powershell
# 1) 환경 (Anaconda 기본 채널은 이용약관 동의가 필요하므로 conda-forge 사용)
conda create -n worklog --override-channels -c conda-forge python=3.12 nodejs=22
conda activate worklog
pip install -r backend/requirements-dev.txt

# 2) 화면 빌드
cd frontend; npm ci; npm run build; cd ..

# 3) 테스트
python -m pytest                      # 백엔드 (약 2분)
cd frontend; npx tsc --noEmit; npx vitest run

# 4) 실행 (또는 실행.bat)
python backend/run.py                 # http://localhost:8000/
```

화면 개발 서버: `cd frontend; npm run dev` (Vite 가 `/api` 를 `127.0.0.1:8000` 으로 프록시. 백엔드를 따로 띄워야 함).

### 운영 PC (Node.js 불필요)

1. `scripts\package.ps1` 로 만든 zip 을 풀고 `config\config.example.json` → `config\config.json` 복사 후 수정
2. **`초기설정.bat`** 더블클릭 → Python 환경을 **Conda → embedded → venv** 순서로 시도해 먼저 성공한 하나를 준비한다(실행.bat 이 찾는 순서와 같음).
   - Conda: Miniconda/Anaconda 가 있으면 env `worklog`(conda-forge, Python 3.12)를 만들거나 이미 있으면 패키지만 맞춘다. base 환경은 바꾸지 않고 Anaconda 약관에 대신 동의하지 않는다.
   - embedded: `runtime\python\` 에 Python 3.11+ “Windows embeddable package” 를 풀어 두었을 때만. `import site` 를 켜고(원본 `.orig` 보관) pip·패키지를 설치한다.
   - venv: PC 의 Python 3.11+ 로 `.venv` 를 만들고 패키지를 설치한다.
   - 인터넷이 없으면: 인터넷 되는 PC 에서 `scripts\make-wheelhouse.ps1` 로 `wheels` 폴더를 만들어 프로그램 폴더에 두면 자동으로 오프라인 설치한다. 옵션: `-Only conda|embedded|venv`, `-WheelDir 경로`, `-Dev`(개발 PC: 테스트 패키지 + Node.js), `-DryRun`(계획만 표시).
3. `실행.bat` 더블클릭 → 표시된 주소로 접속. 창을 닫으면 종료. 자동 시작·서비스·자동 재시작 없음.

### 편의 실행 파일 (프로젝트 폴더 루트)

| 파일 | 용도 |
|---|---|
| `초기설정.bat [-Only ...] [-WheelDir ...] [-Dev] [-DryRun]` | 처음 한 번: Python 환경을 Conda → embedded → venv 순서로 준비(먼저 성공한 하나). 데이터·설정은 건드리지 않는다. 패키지가 바뀐 업데이트 뒤에 다시 실행해도 된다 |
| `실행.bat` | 운영 서버 실행 (`config\config.json` 의 포트/데이터 폴더 사용) |
| `테스트실행.bat [포트]` | **테스트용 서버**: 기본 포트 `8100`, 데이터는 `data_test\` 로 분리되어 운영 서버/데이터를 건드리지 않는다. 포트가 이미 사용 중이거나 Windows 예약 포트면 실행 전에 알려 준다. 기본값은 파일 위쪽 `set` 두 줄에서 바꾼다 |
| `빌드.bat [-Clean] [-Test] [-Package]` | 화면 빌드(개발 PC, Node 필요). Node 가 PATH 에 없으면 Conda `worklog` 환경에서 찾는다. `-Clean` 은 `node_modules` 재설치, `-Test` 는 타입체크+단위 테스트 후 빌드, `-Package` 는 빌드 후 배포 zip 생성. 개발 서버(`npm run dev`)가 떠 있으면 먼저 종료해야 한다 |
환경 탐색 순서는 **Conda → embedded → venv** 이고 처음 정상인 후보를 쓴다(`scripts/select-python.ps1`). 앱 오류가 나면 다른 Python 으로 다시 실행하지 않고 원인을 출력한다. base 환경은 설치/수정하지 않는다.
업데이트는 `배포.bat` 으로 하거나 새 zip 을 같은 폴더에 덮어 풀면 된다(`data\`, `config\config.json` 은 zip 에 없다). **데이터를 프로그램 폴더 밖에 두려면** `config\config.json` 의 `DATA_DIR` 에 절대경로(예: `D:\\WorklogData`)를 지정하면 폴더를 교체해도 영향이 없다.

## 설정 (`config/config.json`, 환경변수 `WORKLOG_<KEY>` 가 우선)

| 키 | 기본값 | 설명 |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 외부 공개 범위는 Windows 방화벽/사내망 정책에 따름. 프로그램은 방화벽을 바꾸지 않는다. 예약 포트는 `netsh interface ipv4 show excludedportrange protocol=tcp` 로 확인 |
| `DATA_DIR` | `data` | 상대경로는 **프로그램 폴더** 기준(실행 위치 무관) |
| `BACKUP_DIR` | `<DATA_DIR>\backups` | 가능하면 다른 드라이브 |
| `BACKUP_RETENTION_COUNT` | `14` | 성공한 최근 N개 보관. 휴지통은 자동 영구 삭제 없음 |
| `TEMP_ATTACHMENT_RETENTION_DAYS` | `7` | 참조되지 않는 임시 첨부만 정리 |
| `CONDA_ENV_NAME` / `EMBEDDED_PYTHON_PATH` / `VENV_PYTHON_PATH` | `worklog` / `runtime/python/python.exe` / `.venv/Scripts/python.exe` | 런처 탐색 후보 |
| `TIMEZONE` | `Asia/Seoul` | 업무 날짜 기준 |
| `BACKUP_HARDLINK_ATTACHMENTS` | `false` | 공간 절약용. 켜면 원본 손상이 백업에도 번질 수 있음 |
| `AI_API_URL` / `AI_API_KEY` / `AI_MODEL` | 비어 있음 | 보고자료 AI. 주소·키가 모두 있으면 서버가 직접 호출, 없으면 붙여넣기 방식. 키는 화면에 노출하지 않음 |
| `AI_TIMEOUT_SECONDS` | `120` | AI 호출 한 번의 제한 시간 |
| `REPORT_JOB_RETENTION` | `200` | 보관할 보고자료 작업 수(넘으면 오래된 결과부터 삭제) |

이 외 `SQLITE_SYNCHRONOUS`(기본 FULL), `SQLITE_BUSY_TIMEOUT_MS`(5000), `EXPORT_WORKER_ENABLED` 가 있다.

## 저장소 구조

```text
backend/app/        api/ (얇은 라우트) · services/ (업무 로직·트랜잭션) · models.py · schemas.py · documents.py · achievements.py · workers.py
backend/weekly_report/  PPT 생성기 (weekly-report 프로젝트에서 가져옴, 변경점은 VENDORED.md)
backend/report_assets/  PPT 템플릿·프롬프트·스키마·설정·LG스마트체(줄 수 계산용)
backend/migrations/ Alembic (0001 초기 스키마, 0002 TASK 이름)
frontend/src/       editor/ (Tiptap 확장·노드뷰) · gantt/ (Frappe 어댑터) · drafts/ (IndexedDB 초안 로직) · features/ (화면) · api/
scripts/            select-python.ps1 · setup-venv.ps1 · make-wheelhouse.ps1 · package.ps1 · loadtest.py · kill_restart_check.py · gen_*.py
tests/              pytest (API 통합·동시성·fault injection·런처)
config/             config.example.json   (config.json 은 Git 제외)
data/               런타임 데이터(DB·json·attachments·backups·exports·logs·reports) — Git 제외, 업데이트로 덮어쓰지 않음
실행.bat            수동 실행기
```

계층: API(요청 검증) → Service(짧은 쓰기 트랜잭션, 파일 처리는 트랜잭션 밖) → SQLAlchemy. 편집기와 간트는 어댑터 경계(`editor/`, `gantt/`) 안에 둔다.

## API 규칙 요약

`/api/v1`, camelCase. 변경 요청은 `Idempotency-Key` 필수, 대부분 `X-Actor-Id`(선택 작성자, 인증 아님)와 `expectedRevision` 필요. 충돌은 409(`REVISION_CONFLICT`, `LOG_EXISTS`, `LOG_IN_TRASH`, `STATE_CONFLICT` …), 검증은 422(`fieldErrors`), 일시적 저장소 혼잡은 503(같은 키로 재시도). 구현 시 확정된 세부는 [docs/05_API_SPEC.md](docs/05_API_SPEC.md) 의 “구현 반영” 절 참고.

## 데이터 구조 변경 / migration

Alembic `0001_initial_schema` + `0002_task_title`(TASK 이름 컬럼) 이 전체 스키마다. 서버 시작 시 자동으로 `upgrade head` 한다. **스키마를 바꾸면 새 revision 을 추가**해야 하며(기존 파일 수정 금지), 복원할 백업의 `schemaVersion` 이 프로그램보다 새로우면 복원을 거부한다.

## 문서

| 문서 | 책임 |
|---|---|
| [docs/01~06](docs/) | 백서·UX·아키텍처·데이터 모델·API·저장/운영 (설계, 구현 반영 절 추가됨) |
| [docs/07_DEVELOPMENT_PLAN.md](docs/07_DEVELOPMENT_PLAN.md) | 단계별 상태와 남은 작업 |
| [docs/08_DECISIONS.md](docs/08_DECISIONS.md) | 결정 원장 (확정/철회/구현 기본값/변경 기록) |
| [docs/09_PROMPT.md](docs/09_PROMPT.md) | 개발 시작 프롬프트 |
| [docs/10_VERIFICATION_REPORT.md](docs/10_VERIFICATION_REPORT.md) | 구현·검증 보고서 (확인한 것/못한 것) |
| [docs/11_WINDOWS_SMOKE.md](docs/11_WINDOWS_SMOKE.md) | 운영 PC 스모크 체크리스트 |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | 의존성 라이선스 목록 (`scripts/gen_notices.py`) |
