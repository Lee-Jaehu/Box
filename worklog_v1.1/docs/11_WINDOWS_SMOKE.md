# Windows 운영 PC 스모크 체크리스트

개발 PC 에서 자동 검증하지 못한 항목([10_VERIFICATION_REPORT.md](10_VERIFICATION_REPORT.md) §7)을 운영 PC 에서 사람이 확인하기 위한 절차다. 각 항목의 결과를 ☐ → ☑ 로 기록하고, 실패하면 증상·화면·`data\logs\worklog.log` 를 남긴다.

## A. 설치 (Node.js 불필요)

1. 릴리스 zip(`scripts\package.ps1` 결과)을 설치 폴더에 푼다. 업데이트일 때는 **같은 폴더에 덮어 푼다** — zip 에는 `data\`, `config\config.json` 이 없으므로 사용자 데이터·설정이 지워지지 않는다.
2. `config\config.example.json` 을 `config\config.json` 으로 복사하고 필요하면 `PORT`, `DATA_DIR`, `BACKUP_DIR` 를 고친다. **백업은 가능하면 다른 드라이브**를 지정한다.
3. Python 환경을 하나 준비한다(우선순위: Conda → embedded → venv). **`초기설정.bat` 을 더블클릭하면 이 순서로 자동 시도**하고 마지막에 `실행.bat` 이 쓸 환경을 보여 준다(`[setup] launcher (run .bat) will use: ...`). 실패하면 `[setup]` 줄에 이유가 나온다. 아래는 직접 할 때의 방법이다.
   - Conda: `conda create -n worklog --override-channels -c conda-forge python=3.12` 후 `pip install -r backend\requirements.txt`
   - venv: PowerShell 에서 `.\scripts\setup-venv.ps1` (오프라인이면 개발 PC 에서 `.\scripts\make-wheelhouse.ps1` 로 만든 `wheels\` 를 복사하고 `-WheelDir .\wheels`)
   - embedded: `runtime\python\python.exe` (직접 구성. `_pth`/site-packages/네이티브 wheel 포함 여부를 §E 로 확인)
4. (선택) 운영 서버와 별도로 시험하려면 테스트실행.bat [포트] 를 쓴다(데이터는 data_test\ 로 분리).
5. 포트 확인: `netsh interface ipv4 show excludedportrange protocol=tcp` 에 사용할 포트(기본 8000)가 **없어야** 한다. 있으면 `config.json` 의 `PORT` 변경(예약 포트는 `WinError 10013` 으로 서버가 종료된다).

- ☐ 3 의 방법으로 만든 환경에서 `실행.bat` 이 `[Worklog] Python (conda|embedded|venv): …` 를 출력하고 서버가 시작된다
- ☐ 한글·공백이 들어간 폴더(예: `D:\업무 도구\worklog`)에서도 동일하게 시작된다
- ☐ 환경이 하나도 없을 때 원인 목록(`[conda]`, `[embedded]`, `[venv]`)이 보이고 창이 바로 닫히지 않는다
- ☐ 서버 시작 후 일부러 포트를 점유해 오류를 내면 원인이 출력되고 **다른 Python 으로 자동 재실행되지 않는다**

## B. 접속

- ☐ 서버 PC 브라우저에서 `http://localhost:8000/` 이 열린다
- ☐ 실행 창에 표시된 `http://<서버 IP>:8000/` 로 **다른 PC**에서 열린다 (안 되면 Windows 방화벽 인바운드 규칙을 **운영자가 수동으로** 허용. 프로그램은 방화벽을 바꾸지 않는다)
- ☐ 서버 PC 절전/잠금 후 접속 불가가 정상임을 사용자에게 안내했다(자동 전원 설정 기능 없음)
- ☐ 실행 창을 닫으면 서버가 종료되고, 다시 `실행.bat` 을 실행하면 데이터가 그대로 있다(자동 재시작/서비스 없음)

## C. 기본 업무 흐름 (사용 브라우저마다 반복: Edge, Chrome)

- ☐ 조직·사용자 등록 또는 Excel/CSV 가져오기 → 오류 행이 있으면 **아무 것도 적용되지 않고** 행 번호와 이유가 보인다
- ☐ 상단 작성자 선택 → 프로젝트 생성(‘일반·수시 업무’ 자동 생성) → 마일스톤 이름만으로 빠른 추가
- ☐ 업무일지 작성 → 저장 → 새로고침해도 내용이 그대로 → 다른 PC 에서 같은 일지가 보인다
- ☐ 저장하지 않고 새로고침 → “임시저장 복구” 배너 → 복구 내용이 맞다
- ☐ 두 PC 에서 같은 일지를 열고 한쪽이 저장한 뒤 다른 쪽이 저장 → 충돌 안내, 내 입력 유지
- ☐ 이미지 첨부(드롭/붙여넣기/버튼) → 설명 없이 저장하면 막히고, 입력하면 저장된다
- ☐ 20MB 가까운 PDF 첨부와 21MB 파일 거부 메시지
- ☐ To-Do 완료 + “오늘 한 일에도 남기기”, Issue → 대응 To-Do → To-Do 완료가 Issue 를 자동 해결하지 않음
- ☐ 휴지통 이동/복원, 프로젝트 삭제 후 복원 시 하위 기록이 돌아온다
- ☐ 운영 탭: 지금 백업 → 목록에 성공으로 표시, `data\json` 에 `daily.json` 이 생긴다

## D. 편집기 (개발 PC 에서 **미실시**였던 항목)

- ☐ **한글 IME**: 한글 조합 중 Enter/Backspace/방향키, 목록(•/1./☑)에서 한글 입력 후 Enter 로 다음 항목, 빈 항목 Enter 로 목록 종료, 표 셀 안 한글 입력, TASK 카드 여러 개를 오가며 입력해도 글자가 깨지거나 사라지지 않는다
- ☐ 표 삽입(크기 선택) 후 마우스로 열 너비 조절, 행/열 추가·삭제, 셀 드래그 선택 후 **병합/분할** → 저장 → 재열기에서 같다
- ☐ **Excel 에서 표 영역 복사 → 편집기에 붙여넣기**: 행·열·셀 값이 유지된다(서식·수식은 유지되지 않음이 정상). 큰 표(예: 30×10)도 확인
- ☐ 간트: 날짜 선택으로 작업 추가, **마우스로 막대 이동/양 끝 조절**, 일/주/월 전환 → 저장 → 재열기에서 날짜가 같다
- ☐ 공용 간트(기준정보): 막대를 끌면 ‘현재 계획’만 바뀌고 확정 기준·실제일은 그대로

## E. embedded Python 을 쓰는 경우만

- ☐ `runtime\python\python._pth` 에서 `import site` 가 활성화되어 있고 `Lib\site-packages` 가 포함된다
- ☐ `runtime\python\python.exe -c "import fastapi, uvicorn, sqlalchemy, alembic, pydantic, openpyxl, PIL, multipart"` 성공
- ☐ 위 A~C 를 이 환경으로 반복

## F. 장애·복구

- ☐ 서버 창을 작업 관리자로 강제 종료 → 다시 실행 → 직전 저장 내용이 있고, 잠시 뒤 `data\json` 사본이 갱신된다
- ☐ 운영 탭에서 백업 복원 → 복원 직전 백업이 목록에 남고, 복원 후 다른 PC 브라우저의 오래된 임시저장 초안은 “복원 이전 초안” 안내로 뜬다(자동 저장·반영 안 됨)
- ☐ 백업 폴더(`data\backups` 또는 `BACKUP_DIR`) 에 최근 성공 14개만 남는다

## G. 재현용 명령 (개발자)

```powershell
# 런처 선택 순서·한글/공백 경로·앱 오류 후 재시작 없음
python -m pytest tests\test_launcher.py
# 강제 종료 후 export 재개 (임시 data 폴더와 사용 가능한 포트 지정)
python scripts\kill_restart_check.py $env:TEMP\wl-kill 18766
# 20명 부하 (서버를 임시 data 폴더로 띄운 뒤)
python scripts\loadtest.py --base http://127.0.0.1:8001 --users 20 --rounds 4 --think 3
```

## H. 보고자료(PPT)

- [ ] 상단 **보고자료** 탭이 보이고, 위쪽 안내가 AI 설정 상태(서버 연결 / 붙여넣기 방식)와 맞다.
- [ ] 주간 보고: 기준 일자를 바꾸면 주차·기간(월~일) 표시가 바뀌고, 이전 주/다음 주 버튼이 동작한다.
- [ ] 담당 조직·팀 필터 → ‘필터 적용’ → 프로젝트 여러 개 체크 → PPT 만들기 → 과제 순서대로 한 파일에 들어 있다.
- [ ] 붙여넣기 방식: ‘프롬프트 복사’가 사내 주소(http)에서도 동작한다(막히면 칸을 직접 선택해 복사 안내). 사내 AI 응답을 그대로 붙여 넣어 끝까지 진행된다.
- [ ] 서버 AI 연결(설정한 경우): `config.json` 의 `AI_API_URL`·`AI_API_KEY` 설정 후 재시작 → 붙여넣기 없이 완료된다. 실패하면 화면 오류 문구와 `data\logs\worklog.log` 를 확인한다(키는 로그에 남지 않음).
- [ ] 기간 보고: ‘선택한 프로젝트 기간으로’, 경영진 1장 요약 양식 ↔ 주간업무 양식 모두 생성된다.
- [ ] 월간 종합이 생성되고 제목의 조직명이 고른 팀/담당과 같다.
- [ ] 참고 슬라이드: 업무일지에 넣은 표·간트와 마일스톤 일정이 PowerPoint 에서 표·도형으로 열리고 고칠 수 있다.
- [ ] 운영 PC 의 PowerPoint 에서 LG스마트체로 보인다(미설치 PC 는 다른 글꼴로 보임).
