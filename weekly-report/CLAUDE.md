# 주간업무 자동화 – 주간 정리 모듈 & PPT 생성기

## 목적
사내 Worklog 웹에 쌓인 Daily(업무 메모) JSON을 주간 단위로 정리하고(EXAONE API),
회사 주간업무 PPT 양식에 자동으로 채운다. 그룹장 시연용이다.

## 범위
- 이 저장소는 두 모듈만 만든다.
  1. `weekly` : Daily 원문 → 주간 정리본(weekly.json) + 누적 요약(cumulative.json)
  2. `pptgen` : 기준정보 + weekly + cumulative → 주간업무 PPT
- Worklog 웹은 다른 개발자가 만든다. `data/master`, `data/raw` 는 **읽기만** 하고 절대 쓰지 않는다.
  우리가 쓰는 곳은 `data/derived` 와 `output/` 뿐이다.
- 구현 순서: pptgen 먼저 (data/derived 예시로 개발) → weekly 다음.

## 폴더
- `docs/` : 설계 문서 (INTERFACE_SPEC.md, 결정사항_요약.md, CLAUDE_CODE_작업순서.md)
- `schemas/` : 모든 JSON 형식. 출력 JSON은 반드시 스키마 검증 통과
- `config/` : 법인·공정 코드표, 업무 유형별 마일스톤 템플릿
- `templates/` : PPT 양식 v2, 완성 예시 (현재 실제 위치: weekly-report/주간업무PPT_Template_v2.pptx, weekly-report/완성 예시 PPT.pptx)
- `prompts/` : EXAONE 프롬프트 원문(.txt)과 mock 응답 (prompts/README.md 참고)
- `data/master/projects/` : 기준정보 (예시 P-ASM-001)
- `data/raw/daily/{yyyy}/{yy-mm-dd}/` : Daily 원문
- `data/derived/weekly/{project_id}/{week}.json`, `data/derived/cumulative/{project_id}/{week}.json` : 정리 결과
  (2026-W39 파일 = weekly 모듈의 기대 출력이자 pptgen 개발용 입력, 2026-W38 누적 요약 = weekly 모듈의 이전 주 입력)
- `output/` : 생성된 PPT

## 시연 범위에서 생략하는 것
- 변경 제안 승인, 주간 정리본 검토(review) 절차는 만들지 않는다.
- Daily마다 AI 정리하지 않는다. 주간 마감 때 그 주의 Daily 원문을 한 번에 정리한다.
- 일정 변화(weekly.milestone_updates)는 기준정보 파일에 쓰지 않고, PPT 생성 시 기준정보 위에 덧씌워 적용한다.

## PPT 규칙 (templates/주간업무PPT_Template_v2.pptx)
- 과제 1개 = 슬라이드 1장, 넘치면 "(계속)" 슬라이드 1장까지 (과제당 최대 2장).
- 양식 크기(10.83 × 7.5인치)·서식은 바꾸지 않는다. 칸은 도형 이름으로 찾는다:
  `slide_title, pjt_header, author, updated_at, main_table, body_top, ms_table, body_main`
- main_table 칸: r1c0 과제명, r1c1 대상, r0c2 머리글(주차), r1c2 한 줄 요약, r1c3 완료 목표 일정, r1c4 담당자, r2c2는 비워 둠
- 본문 9pt, 한 항목 = 한 줄, 40~60자(끝의 날짜 포함, 한글 1, 영문·숫자·기호 0.55로 계산), 본문 전체 36줄
- 문체: 요약(headline)·본문 모든 문장은 경어체 "~했습니다/~입니다" (그룹장 보고용, 2026-10-04 결정)
  - 몇 주가 쌓여도 이해되도록 함축하지 않고 대상·내용·결과를 함께 쓴다. 40자 미만·경어체 아님은 검증 보고서에 '주의'
  - 진행 현황·이슈·누적 요약 문장 끝에 진행 날짜 "~했습니다. (10/08)", 기간은 "(09/28~09/30)", 계획은 예정일이 있을 때 "(~10/16)"
    날짜 근거 = 메모 본문 날짜, 없으면 메모 작성일(기록 ID의 YYMMDD). 날짜가 없으면 검증 보고서에 '주의'
  - 배경/목표는 기준정보(master) 문장을 그대로 쓴다 (읽기 전용이라 문체를 바꾸지 않음)
- 본문 순서·분량: 배경·목표 3줄 → 마일스톤 표 → 진행 현황(누적 최대 8 + 금주 5~7) → 향후 계획 3 → 이슈 2
  - 누적 요약 한도는 마일스톤 표 길이에 따라 줄어든다: 금주·계획·이슈를 먼저 놓고 첫 장에 남는 줄 수(최소 3, 최대 8).
    이 값을 cumulative_update 프롬프트의 max_items로 넘겨 AI가 오래된 항목을 합치게 한다 (2026-10-03 결정)
  - 줄 수 계산: LG스마트체 실측 줄 높이 1.17em, 본문 한 줄 폭은 실제 너비의 92% (LG스마트체 기준 약 62자로 60자 문장이 한 줄에 들어감)
- 폰트: 국문 `LG스마트체 Regular`(ea, TTF 이름과 정확히 일치해야 함), 영문 Arial Narrow(latin). 다른 폰트 금지
  - 글꼴 파일: `fonts/` 또는 weekly-report 폴더의 `LGSM*.TTF`. 템플릿 테마 ea("LG Smart Regular")는 출력 파일에서 보정
- 배경/목표: "[배경/목표]" 굵은 제목 줄 + "- 배경. 목적" 한 문단 (내용 최대 3줄)
- 일정 칸(r1c3): 목표 일정 + 목표일을 넘는 미완료 단계 병기 "(북미 10월초)", 이번 주 바뀐 병기는 파란색
- 작성자·담당자: `config/people.json`(ID → 이름·직급), 담당자 = owner + members
- 변경 표시: 파란색 RGB(0,0,255). 그 외 검정.
  파란색 대상 = weekly 항목 중 changed=true, 이번 주 바뀐 마일스톤 값(milestone_updates), 한 줄 요약
- 마일스톤 표 열: 단계 | 적용 범위 | Baseline | 계획 | 실적 | 상태 | 비고
  - 계획 ≠ Baseline 이면 "MM/DD (+n)" (n = 지연 일수), plan_text가 있으면 그 문구 표시
  - 상태 칸 배경: 완료 E7E7E7, 진행 DDEBF7, 지연 FBE2E2, 예정 FFFFFF
  - 최대 9행, 넘치면 완료된 하위 행(같은 parent_id)부터 "OO 완료 n개 사이트" 한 행으로 접기
  - 적용 범위: config/code_table_site_process.json 코드를 표시명으로 변환, 공통 단계는 "공통",
    표시 형식 "{법인} {라인}·{공정명}" (예: "WA MEB·조립")
- 단계 이름 앞 번호는 붙이지 않는다 (완성 예시 기준, 2026-10-03 결정. 근거: docs/디자인_기준_비교.md)

## 주간 정리 규칙
- EXAONE 호출은 주간 정리(weekly_rollup), 누적 요약(cumulative_update), 분량 줄이기(fit_to_budget, 넘칠 때만) 3가지
- 개발 환경에서는 EXAONE API에 접속할 수 없으므로 클라이언트는 두 모드로 만든다:
  - `mock` (기본값): prompts/mock_responses/{prompt_id}__{project_id}__{week}.json 반환
  - `live`: 환경변수 EXAONE_API_URL, EXAONE_API_KEY 사용
- 프롬프트는 코드에 하드코딩하지 않고 prompts/*.txt 를 읽어 {{변수}}를 치환한다
- 대상 Daily: project_id가 있고 visibility=project, deleted=false, 해당 주(ISO 주차, 월~일)인 것
- AI 출력 검증 (결과는 output/validation_{week}.txt 로 남김):
  - 출력 문장의 숫자(소수, 퍼센트, 날짜 M/D)가 입력 원문·표·기준정보에 있는지
  - source_ids가 입력으로 준 ID 안에 있는지
  - 검증 실패 항목은 저장은 하되 리포트에 표시 (시연에서 보여줄 수 있게)

## 개발 규칙
- Python 3.11, python-pptx, jsonschema (requirements.txt)
- 단계마다 테스트를 만들고 data/ 예시로 실행해 통과시킨 뒤 다음 단계로 간다
- 주석과 로그 메시지는 한국어
- 실제 사내 업무 데이터는 이 저장소에 넣지 않는다 (예시 데이터만 사용)
