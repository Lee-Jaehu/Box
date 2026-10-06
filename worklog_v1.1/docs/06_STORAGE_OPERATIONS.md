# Worklog 파일·실행·운영 명세

## 1. 디렉터리

기본 data root는 프로그램 폴더의 data, 설정으로 절대경로 변경 가능. 실행 CWD가 아니라 launcher 위치 기준으로 해석한다. 코드 업데이트가 data/config를 덮어쓰지 않게 배포한다.

```text
data/
  db/worklog.sqlite3
  json/master/organizations.json
  json/master/users.json
  json/projects/{projectId}/project.json
  json/projects/{projectId}/{YYYY-MM-DD}/daily.json
  json/projects/{projectId}/trackers.json
  attachments/{projectId}/{attachmentId}.{ext}
  backups/{backupId}/
  exports/                 # 전달용 bundles, 사본과 구별
  temp/
  logs/
```

DB의 -wal/-shm 등은 엔진 관리 파일이며 임의 삭제 금지. live DB는 로컬 디스크에 둔다. 백업 위치는 별도 드라이브 가능. JSON은 UTF-8, ensure_ascii=false, 들여쓰기 2, stable ordering. 날짜/작성자 정렬 후 task sortOrder로 출력. 사본을 편집해도 DB로 자동 import하지 않음.

## 2. 내보내기

daily.json에 프로젝트/날짜의 모든 활성 작성자 기록. 기준정보와 tracker는 별도 최신 사본. 삭제/수정·복원 시 해당 target dirty. 파일이 비어야 하는 상황도 logs=[]로 교체하고 최신 sourceRevision 기록. 프로젝트 삭제 상태는 project.json tombstone으로 표시, 보고용 bundle은 삭제 프로젝트 제외.

이미지 fileRef는 data root 기준 상대경로이며 자동 사본 자체는 바이너리를 포함하지 않는다. bundle 다운로드는 DB snapshot+선택 첨부+manifest로 경로를 재배치한다. JSON 사본은 backup이 아님. 내보내기 이력/DB 전체 이력을 완전히 포함하지 않는다.

## 3. 첨부 정책

파일당 20MB(구현 기본값은 20*1024*1024 bytes로 UI 명시). 이미지 PNG/JPEG/WebP 권장, 일반 PDF/XLSX/CSV/DOCX/PPTX/TXT 제안. legacy Office 확장자는 실제 필요 확인 후 allowlist 확장. 임의 실행파일·HTML 업로드 허용하지 않음. SVG 업로드/inline은 MVP에서 제외하고 생성 SVG는 후속 renderer 범위. 일반 문서는 다운로드, 이미지 실제 bytes와 크기/해상도 확인. 원본 파일명은 표시 metadata, 저장 경로는 server UUID. 원본 보존, thumbnail 생성 시 별도 파생물.

파일 크기·이미지 pixel limit·전체 요청 상한 설정. ZIP 기반 Office 파일을 임의 실행/추출하지 않음. 본문 외부 링크와 첨부 content-type 안전 처리. 로그인 없는 구조에서 첨부는 권한으로 보호되지 않음을 UI/운영 문서에 명시.

임시 업로드 후 정식 일지 저장 시 DB 연결을 확정. 미사용 임시 파일 기본 7일 정리 제안. 오래된 IndexedDB 초안에서 첨부가 사라졌다면 본문을 보존하고 재첨부 안내. 휴지통 참조 파일은 임시 정리 대상 아님.

## 4. 명단 가져오기

조직/사용자 각각 xlsx/csv template. 조직은 externalKey, kind, name, parentExternalKey. 사용자 name, teamExternalKey(or teamPath), employeeNumber(optional), externalKey(optional), userId(existing export optional), active(optional).

CSV는 UTF-8/BOM 기본, 다른 인코딩은 선택하거나 읽기 실패 안내. xlsx 수식은 식별자 값으로 실행/추론하지 않고 원본이 모호하면 오류. 엑셀에서 이미 사라진 앞자리 0을 프로그램이 복원할 수 있다고 약속하지 않음. 템플릿 사번 열은 text 형식.

내부 userId → externalKey → 제공된 사번 순으로 명확한 매핑 후보. 이름/팀만으로 자동 merge 금지. 누락 사용자는 자동 삭제/비활성화 안 함. 모든 오류/모호 행을 해결해야 전체 적용 가능. 적용 전 preview와 현재 기준정보 revision 비교. 가져오기와 JSON 갱신 요청은 원자적 저장.

## 5. Windows 수동 실행

확정: 실행.bat, Conda → embedded Python → .venv 순으로 환경 탐색. 자동 부팅 시작·서비스·자동 재시작 없음. Ctrl+C/창 닫기 시 종료. 종료 중 pending 작업은 다음 수동 실행에서 재개.

구현 기본값(사용자가 exact name은 확정하지 않음): conda env worklog, embedded runtime/python/python.exe, fallback .venv/Scripts/python.exe. config로 변경 가능. 자동으로 base 환경 설치/수정 금지.

실행기는 각 후보의 실행 가능/버전/필수 패키지 확인 후 처음 정상 환경 선택. 후보가 없거나 부적합이면 다음 후보와 이유 표시. 정상 환경에서 서버 실행 후 DB/port/애플리케이션 오류가 나면 다른 Python으로 자동 재실행하지 않고 원인 출력.

Windows embeddable Python은 일반 Python+venv와 다르므로 site-packages/_pth/native wheels 포함을 실제 검증한다. 소스 인계에 runtime 바이너리가 있다고 가정하지 않는다. 최초 bootstrap은 설치 스크립트/오프라인 wheel bundle로 분리하고 매 실행 pip install 하지 않음. 운영 PC Node.js 필요 없음, frontend/dist 동봉. Python 최소/권장 버전과 OS architecture는 P0에서 고정.

기본 제안 host 0.0.0.0, port 8000. 실행 화면에 localhost와 서버 IP 기반 접속 주소 표시. 다른 기기 접근은 Windows 방화벽/사내 정책 범위에서 운영자가 설정, 자동 우회/방화벽 변경 금지. 사내 허용 범위에 배포. 서버 PC 종료·절전 동안 접속 불가가 정상이며 자동 전원 설정 기능 제외.

설정 예: DATA_DIR, BACKUP_DIR, HOST, PORT, CONDA_ENV_NAME, EMBEDDED_PYTHON_PATH, VENV_PYTHON_PATH, TIMEZONE=Asia/Seoul, BACKUP_RETENTION_COUNT=14, TEMP_ATTACHMENT_RETENTION_DAYS=7. 실제 값은 구현 후 config.example에 기록.

## 6. 백업·복원

프로그램 실행 중 로컬 날짜별 첫 성공 업무 저장 이후 backup을 예약. 수동 ‘지금 백업’ 지원. 서버가 꺼져 있던 날짜의 가짜 백업을 만들지 않고 다음 실행의 저장/수동 요청 시 처리. 동시에 같은 날짜 백업이 여러 개 예약되지 않게 DB로 상태 관리.

SQLite backup API로 일관된 DB snapshot을 만든 뒤 그 snapshot이 참조하는 정식 첨부(휴지통 참조 포함)를 immutable file ID로 수집한다. 백업 완료 전 참조 파일 물리 삭제 금지. manifest에 파일 hash/size, DB schema version, 생성 시각/instance ID 포함. 누락 파일이 있으면 불완전 상태로 실패 처리, 정상 백업 수에 포함하지 않음.

최근 성공한 백업 14개 보관. 새 백업이 검증 완료된 뒤 초과분 정리. 실패가 이전 정상 백업 삭제를 유발하지 않음. 읽기용 JSON은 DB로 재생성 가능하므로 필수 backup 아님. 설정 포함 시 개인 경로/민감값 별도 취급.

복원: 대상 검증 → 쓰기/worker 정지·maintenance mode → 현재 상태 pre-restore backup → DB 연결 종료 → 준비한 DB/첨부 교체(실패 시 이전 상태 복귀 가능) → schema 호환 확인 → export 전체 dirty → 재개. 복원 완료 후 stale browser drafts는 base revision/instance restore generation을 비교해 자동 저장 금지.

휴지통은 자동 영구 삭제 없음. JSON mirror 삭제는 backup 삭제가 아님. 같은 디스크 백업은 디스크 고장 대비가 아니므로 운영자가 별도 드라이브 경로를 선택할 수 있음.
