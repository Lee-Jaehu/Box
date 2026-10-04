# 주간업무 자동화 시연 (weekly + pptgen)

Python 3.11 기반의 두 모듈입니다.

| 모듈 | 입력 | 출력 |
|---|---|---|
| `weekly` | 해당 ISO 주(월~일)의 Daily 원문·표 값, 지난주 weekly·cumulative | `data/derived/weekly/{과제}/{주차}.json`, `data/derived/cumulative/{과제}/{주차}.json`, `output/{과제}/validation_{주차}.txt` |
| `pptgen` | 기준정보 + weekly + cumulative + v2 템플릿 | `output/{과제}_{주차}.pptx`, `output/{과제}_{주차}_ppt_check.txt` |

`data/master`, `data/raw`는 읽기만 합니다. 결과는 `--out-root` 아래 `data/derived`와 `output`에만 원자적으로 씁니다.

## 설치와 P-ASM-001 / 2026-W39 mock 실행

```bash
cd weekly-report
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

OUT=$(mktemp -d)   # 저장소의 예시 결과를 덮어쓰지 않도록 임시 위치 사용
python -m weekly_report pipeline P-ASM-001 2026-W39 --out-root "$OUT"
#  → $OUT/data/derived/weekly/P-ASM-001/2026-W39.json
#  → $OUT/data/derived/cumulative/P-ASM-001/2026-W39.json
#  → $OUT/output/P-ASM-001/validation_2026-W39.txt   (AI 출력 의미 검증)
#  → $OUT/output/P-ASM-001_2026-W39.pptx            (PPT)
#  → $OUT/output/P-ASM-001_2026-W39_ppt_check.txt   (PPT 재검사·처리 내역)

# 저장소의 예시 derived(W39)로 PPT만 만들기
python -m weekly_report pptgen P-ASM-001 2026-W39 --out-root "$OUT"
```

옵션: `--mode mock|live`(기본 mock), `--template PATH`, `--output PATH`(pptgen), `--root PATH`.
템플릿은 `--template` → `templates/주간업무PPT_Template_v2.pptx` → `weekly-report/주간업무PPT_Template_v2.pptx` 순서로 찾습니다.
저장소 루트의 `../주간업무PPT_Template.pptx`(구 양식)는 v2로 간주하지 않습니다.

미리보기: `python -m weekly_report preview "$OUT/output/P-ASM-001_2026-W39.pptx"` → LG스마트체로 렌더링한 PNG
(LibreOffice Impress·poppler 필요, 시스템 글꼴은 바꾸지 않고 임시 fontconfig 사용).

테스트: `python -m pytest -q` (모든 출력은 임시 디렉터리).
합성 5과제 검증: `python fixtures/weekly-report-fixture-kit/verify_fixtures.py "$PWD"` (현재 34/34 PASS).

## 웹 화면으로 시험해 보기 (회사 Windows PC)

1. `weekly-report` 폴더에서 **`run_web.bat`을 더블클릭**한다.
   처음 한 번은 `.venv`를 만들고 패키지를 설치한다. Python 3.11 이상이 필요하다.
2. 브라우저에 `http://127.0.0.1:8765`가 열린다(이 PC에서만 접속 가능).
3. 과제·주차를 고르고 순서대로 진행한다.
   - **① Daily 메모:** 목록에서 메모를 눌러 고치거나 새 메모를 추가한다. 표는 엑셀에서 복사해 붙여 넣어도 된다.
     개인 메모·삭제 메모는 "제외"로 표시된다.
   - **② 실행:** AI 응답 파일이 없으면 EXAONE에 보낼 프롬프트가 나온다.
     → [프롬프트 복사] → 사내 AI(또는 다른 AI)에 붙여 넣기 → 받은 JSON을 오른쪽에 붙여 넣고 [응답 저장 후 다시 실행].
     주간 정리 → 누적 요약 순서로 두 번 묻는다.
     AI 답에 설명 문장·```json 표시가 섞여 있거나 `{"result": {...}}`처럼 한 겹 감싸져 있어도 JSON 부분만 꺼내 쓴다.
     단계별 필수 키(주간 정리 `headline`, 누적 요약 `items`)가 없으면 저장하지 않고 이유를 칸 아래에 보여 준다.
     예전에 저장된 응답이 형식에 맞지 않으면 그 단계만 다시 붙여 넣게 한다 (다른 단계 응답은 그대로).
     메모를 고쳤다면 [이 주차 AI 응답 지우기] 후 다시 실행해야 새 내용이 반영된다.
     저장소의 프롬프트가 바뀌면(예: v0.5 경어체·40~60자·진행 날짜) 기존 작업공간도 다음 요청에서 새 프롬프트로 맞춰진다.
     이미 받아 둔 AI 응답은 예전 문체이므로 [이 주차 AI 응답 지우기] 후 새 프롬프트로 다시 받는다.
   - **③ 결과:** PPT 다운로드(PowerPoint로 열면 LG스마트체로 보임), 의미 검증 보고서, PPT 재검사 보고서.
4. 모든 입력과 결과는 `workspace/` 폴더(시험용 복사본)에만 저장된다. 저장소 예시 데이터는 바뀌지 않는다.
   [작업공간 초기화]를 누르면 처음 상태(저장소 예시 + W40 데모 메모·응답)로 돌아간다.
   초기화 전 입력한 메모·응답·결과는 `workspace_backups/날짜-시각/`에 백업된다.
   PowerPoint 등에서 열려 있어 지우지 못한 파일은 건너뛰고 화면에 알려 준다.
   작업공간에서 파일이 빠지면(예: 초기화 도중 중단) 다음 요청 때 빠진 파일만 자동으로 다시 채운다(고친 메모는 유지).

- **처음 상태:** P-ASM-001 **2026-W40**은 데모 메모와 응답이 들어 있어 [실행]만 누르면 바로 PPT가 나온다.
  **2026-W41**에 메모를 넣으면 프롬프트 → 응답 붙여넣기 흐름을 시험할 수 있다.
- **같은 기능, 명령어로:** `python -m weekly_report serve [--port 8765] [--workspace DIR] [--no-browser]`
- **PPT를 열어 둔 채 다시 실행하면** Windows가 파일을 잠가 덮어쓸 수 없다. PowerPoint에서 닫고 다시 실행한다.

## WorkLog 연동 (업무기록 시스템 export)

동료가 만든 WorkLog의 export JSON을 `data/worklog/` 아래(하위 폴더 포함)에 두면 그대로 읽습니다. 파일 구분은 `fileType`으로 합니다.
- 과제 목록에 WorkLog 과제가 함께 나옵니다.
- 업무일지 1건(작성자별 하루 기록)이 Daily 1건이 됩니다. 수행 task·이슈·할 일·배운 점을 구조 그대로 AI에 보냅니다.
- 마일스톤 일정·상태는 WorkLog 값을 씁니다. 지난주 대비 바뀐 값만 파란색입니다.

```bash
python demo/run_demo.py demo/worklog 00000000-0000-4000-8000-000000000001 2026-W40   # 익명 예시
python -m weekly_report pipeline 00000000-0000-4000-8000-000000000001 2026-W40
```

필드 대응·계산 규칙·동료에게 요청할 항목: `docs/WorkLog_연동.md`

## 보고 자료 (경영진 1장 요약 · 월간 종합, 템플릿 초안)

장표모음집 분석(`docs/보고자료_양식_분석.md`)을 바탕으로 만든 초안입니다. 표·숫자·색은 Rule이 기준정보로 채우고, EXAONE은 칸별 문장만 씁니다.
- 헤드메시지·결론은 경어체로, 본문은 개조식으로 씁니다.
- 검사를 통과하지 못한 칸은 Rule 값으로 대체하고 `*_check.txt`에 남깁니다.

```bash
python demo/report/run_report_demo.py                         # 데모: demo/report/out/*.pptx, preview/*.png
python -m weekly_report report exec P-ASM-001 2026-W40        # 경영진 1장 요약 (mock 응답 필요)
python -m weekly_report report monthly 2026-09                # 월간 종합 (전체 과제)
python tools/make_report_template.py                          # 템플릿 초안 다시 만들기
```

웹 화면에서는 ② 카드의 "보고 자료 생성"을 누릅니다. 종류는 경영진 1장 요약(선택 과제·주차) 또는 월간 종합(그 주차가 속한 달, 전체 과제)입니다.
흐름은 주간 정리와 같습니다: 프롬프트 복사 → EXAONE → 응답 붙여넣기.

## Rule과 AI의 역할 분리

정확도를 위해 **배치·색·분량 판정·검증은 전부 코드(Rule)**가 하고, AI(EXAONE)는 문장만 다룹니다.

| 단계 | AI가 하는 일 | 코드가 하는 일 |
|---|---|---|
| weekly_rollup | Daily 원문 → headline·진행·계획·이슈·milestone_updates 문장 | 대상 Daily 선택, 프롬프트 변수 구성, 응답을 payload로 받아 스키마 필드 채움, **changed 최종 판정**(지난주 정리본 비교), 근거·수치 검증 |
| cumulative_update | 지난 누적 + 이번 주 → 누적 요약 문장 | **고정 사실(pinned_facts) 보존**(AI가 빠뜨리거나 바꿔도 이전 값 유지), new_pinned_facts 중복 없이 병합 |
| fit_to_budget (넘칠 때만) | 칸 한도에 맞게 문장 축약 | 결과 검증(근거 ID ⊂ 원본, 새 수치·날짜·코드 금지, 60자, 누락 없음), **changed·kind 승계**, 실패 시 원문 유지 + (계속) 이월 |
| PPT | 없음 | 칸 매핑, 마일스톤 표·접기·지연일 계산, 파란색 판정, 줄 수 계산, 페이지 나누기, 재검사 |

### PPT 규칙 구현 요약 (`weekly_report/ppt/`)

- `render.py`: 도형 이름으로 칸을 찾고, 템플릿 문단·글자 서식(rPr)을 복제해 글자를 바꿉니다. ea=`LG스마트체 Regular`, latin=`Arial Narrow`, 크기는 템플릿 값(본문 9pt)을 그대로 쓰고, 바꾸는 것은 색(파랑 0000FF / 검정)뿐입니다. 마일스톤 표는 템플릿 데이터 행을 복제해 행 수만큼 만들고, 상태 칸 배경(완료 E7E7E7·진행 DDEBF7·지연 FBE2E2·예정 FFFFFF)을 칠합니다. 본문 도형은 표 높이에 맞춰 세로로 다시 배치합니다(겹침 없음).
- `milestones.py`: `milestone_updates`는 기준정보의 **메모리 복사본**에만 적용합니다(baseline·파일 불변). null/없는 ID, 날짜 형식·실존 여부, 상태값, 문자열 타입을 검사해 잘못된 값은 적용하지 않고 보고합니다. 계획 칸은 `plan_text` 우선, 아니면 plan≠baseline일 때 `MM/DD (+n)`(n은 코드가 계산, 보고서에 "계산값"으로 표시). 9행 초과 시 같은 parent의 완료 하위 행을 "OO 완료 n개 사이트"로 접고, 그래도 넘치면 (계속) 장으로 이월합니다(행을 버리지 않음).
- `budget.py`: 누적 요약 한도를 **마일스톤 표 길이에 맞춰** 정한다(첫 장에 남는 줄 수, 최소 3·최대 8). 같은 값을 주간 정리 단계의 cumulative_update `max_items`로 넘겨 AI가 오래된 항목을 합치게 한다. 줄 높이는 LG스마트체 실측 1.17em, 줄 폭은 실제 본문 너비의 92%로 계산한다. 한글 1 / 영문·숫자·기호 0.55 가중 길이로 **실제 줄 수**를 계산하고 **항목 수**와 따로 검사합니다. 본문 가용 줄 = min(템플릿 영역의 물리 높이, 36줄 규칙 − 배경/목표 − 표 행). 글꼴을 줄이거나 도형 밖으로 넘기지 않고, fit_to_budget → (계속) 장 순서로 처리합니다. 과제당 2장을 넘으면 오류입니다.
- `inspect.py`: 저장한 PPT를 다시 열어 슬라이드 수, 모든 글자의 9pt·글꼴, 허용 색, **파란 글자 집합 = 기대 집합**, 표 값·상태 배경, 영역 경계를 확인합니다.
- 파란색: headline, changed=true 항목, 이번 주 milestone_updates로 실제 바뀐 칸(같은 값으로의 "변경"은 제외). 누적 요약·고정 사실·기준정보는 검정.

### LG스마트체 (`weekly_report/fonts.py`)

- 글꼴 파일: `fonts/` 또는 이 폴더의 `LGSM*.TTF`(Regular·Bold·SemiBold·Light). fontTools로 이름과 실측값을 읽는다.
- 모든 글자의 ea = `LG스마트체 Regular`(TTF nameID 1과 같은 이름). 템플릿 테마의 잘못된 ea(`LG Smart Regular`)는 **출력 파일에서만** 보정한다.
- 표 칸 줄 수는 실측 한글 폭(0.891em)으로 계산한다. 글꼴 파일이 없으면 1.0em으로 보수적으로 계산한다.
- PPT 재검사에서 모든 글자·테마의 ea를 확인하고, check 보고서 `[글꼴]` 절에 사용한 파일을 남긴다.
- PPTX에 글꼴을 임베드하지 않는다. 열어 보는 PC에 LG스마트체가 설치되어 있어야 한다(사내 표준 글꼴 전제).
  글꼴 파일은 "All rights reserved"이므로 저장소 공개 범위를 확인해야 한다.
- 완성 예시와 비교한 디자인 기준은 [docs/디자인_기준_비교.md](docs/디자인_기준_비교.md)에 정리했다.

### 의미 검증 (`weekly_report/validate.py`)

구조(JSON Schema) 오류는 저장하지 않습니다. 구조는 맞고 의미가 틀린 항목은 시연 규칙대로 저장하고 보고서에 `오류/주의/정보`로 표시합니다.
수치·M/D 날짜·코드·호기 표기를 하드코딩 예외 없이 **출처 태그**로 구분합니다:
`원문`(이번 주 Daily·표) / `기준정보` / `계산값`(주차·날짜 범위·지연일) / `이전요약`(지난주 누적·정리본에만 있음 = 원문 미확인) / 미확인(환각 의심 → 오류).
`0.230`과 `0.23`처럼 숫자는 같고 표시 정밀도만 다른 경우는 별도로 기록합니다. `ES…` 사이트 표기는 코드표 별칭 규칙으로 확인하고, 확정할 수 없는 `ESMI1`은 정상 코드로 처리하지 않고 경고합니다.

### EXAONE 클라이언트 (`weekly_report/ai.py`)

- mock(기본): `prompts/mock_responses/{prompt_id}__{project_id}__{week}.json`, fit_to_budget은 `…__{week}__{slot}.json`. mock 파일이 없으면 fit_to_budget은 원문 유지로 처리합니다.
- live: `EXAONE_API_URL`, `EXAONE_API_KEY`(선택 `EXAONE_MODEL`). 요청·응답 변환은 `Adapter`로 분리했고 현재는 Chat Completions 형식 가정입니다. **사내 API 계약을 받지 못해 실제 연결은 검증하지 않았습니다.** JSON 파싱 실패 시 문서 문구로 1회 재요청, 타임아웃·HTTP·연결 오류는 키를 포함하지 않는 `AIError`로 보고합니다.
- 프롬프트 원문은 `prompts/*.txt`에서 읽고 `{{변수}}`만 치환합니다. 변수 형식은 `prompts/README.md`를 따릅니다(`weekly_report/prompt_vars.py`).

## 확인된 문서·예시 불일치와 처리 방식

| 항목 | 내용 | 처리 |
|---|---|---|
| 시연 범위 | INTERFACE_SPEC 본문 흐름·체크리스트에는 review/변경 제안/Daily별 AI가 남아 있음 | CLAUDE.md·INTERFACE_SPEC 상단의 최신 시연 범위 적용 (구현 안 함) |
| config 위치 | 인터페이스 문서는 `data/master/codes`, 실제는 `config/` | 실제 `config/`를 읽기 전용으로 사용 |
| PPT 출력 위치 | CLAUDE.md `output/`, 인터페이스 트리 `derived/ppt` | `output/` 사용 |
| 템플릿 위치 | CLAUDE.md는 `templates/주간업무PPT_Template_v2.pptx`, 실제 파일은 `weekly-report/` 바로 아래 | 두 위치를 순서대로 탐색 (파일 이동 안 함) |
| 완성 예시 | CLAUDE.md는 `templates/주간업무_예시_…W39.pptx`, 실제는 `weekly-report/완성 예시 PPT.pptx` | 비교 결과와 반영 사항은 docs/디자인_기준_비교.md |
| validation 파일명 | CLAUDE.md `output/validation_{week}.txt`는 과제끼리 덮어씀 | `output/{과제}/validation_{week}.txt` |
| prompt 버전 | 예시 W39 JSON·mock은 v0.1 표기, 프롬프트 문서는 v0.2 | 새 결과는 실제 읽은 버전(v0.2) 기록. 예시 파일은 수정하지 않음 |
| 예시 mock 근거 | weekly mock이 존재하지 않는 `CP-260922-001`을 근거로 사용 | 수정하지 않고 저장, 보고서에 `오류`로 표시 |
| 사이트 표기 | mock 문장의 `ESMI1`(MI1 미확정, 인터페이스 §8-6) | 정상 코드로 처리하지 않고 `주의` 표시 |
| 0.230 / 0.23 | Daily 본문 0.230, 표 값 0.23 | 숫자 동등·표시 정밀도 차이로 `정보` 기록 |
| 이전 누적 근거 | W38 누적 항목 근거가 과제 ID뿐 | `이전요약` 태그로 원문 확인 사실과 구분, 검증됐다고 주장하지 않음 |
| 고정 사실 표시 | 템플릿은 누적 요약에 고정 사실의 핵심 수치 포함을 요구, cumulative는 items/pinned_facts를 분리 | items에 핵심 수치가 이미 있으면 생략, 없으면 누적 요약 끝에 검정으로 추가 |
| 작성자 | 템플릿은 "이름 직급", 기준정보에는 사용자 ID만 있음 | `config/people.json` 매핑(예시 값), 없으면 ID 표시 + 경고 |
| 과제 번호 (n/N) | 의미 미정의 | 덱 안의 과제 순번/전체 수로 해석(단일 과제 = 1/1), 2장째는 "(계속)" |
| 일정 칸 | 템플릿 r1c3 "(변경 시 파란색)", weekly 계약에는 기간 변경 필드 없음 | 목표 일정은 검정, 목표일을 넘는 단계 병기는 이번 주 바뀌었으면 파랑 |
| 단계 번호 | CLAUDE.md는 "6-1." 형식, 완성 예시는 번호 없음 | 완성 예시를 따라 번호 없음 (CLAUDE.md 갱신) |
| 테마 글꼴 | 템플릿 테마 ea `LG Smart Regular` ≠ 실제 TTF 이름 `LG스마트체 Regular` | 출력 파일에서 보정 |

## 남은 차단 요인

1. EXAONE live API 계약(요청/응답 형식, 인증)이 없어 live 연결은 검증되지 않았습니다.
2. 미리보기의 영문은 Arial Narrow 대신 같은 폭 비율의 Liberation Sans로 렌더링합니다. 실제 PowerPoint 화면과 줄바꿈이 조금 다를 수 있습니다.
3. 줄 수 계산은 한글 1자=9pt 폭 가정의 보수적 추정입니다. 실제 PowerPoint 줄바꿈보다 적게 담길 수는 있어도 넘치지는 않도록 설계했습니다.
