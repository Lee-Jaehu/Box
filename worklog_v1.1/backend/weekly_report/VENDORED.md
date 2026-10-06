# weekly_report (가져온 패키지)

출처: `D:\claude\weekly-report\weekly_report` (2026-10-04 사본, 원본 테스트 85개 통과·2개 건너뜀 확인 후 복사).
원본 저장소의 설정·스키마·프롬프트·템플릿은 `backend/report_assets/` 로 옮겼다 (예시 mock 응답·예시 데이터는 가져오지 않음).
Worklog 서비스 연결 코드는 `backend/app/services/reports.py`, 참고 슬라이드(표·간트)는 `backend/app/services/report_slides.py`.

원본을 다시 가져올 때는 아래 변경을 함께 옮겨야 한다. 코드 안에는 `[Worklog 통합]` 주석으로 표시했다.

| 파일 | 변경 | 이유 |
|---|---|---|
| ai.py | `ExaoneClient(api_url, api_key, model)` 인자 추가(없으면 기존처럼 환경변수 EXAONE_*) | 서버 설정(config.json `ai_api_url`/`ai_api_key`)으로 모든 사용자가 같은 AI 연결을 쓰게 |
| ai.py | `period_rollup` 응답 형식 추가, 단계 혼동 안내를 주간·기간 정리 모두에 적용 | 기간 보고 |
| weekly.py | `run_weekly(..., period=(시작, 끝), response_key=...)`, `select_dailies(..., period)`, `iso_week()` | 임의 기간을 한 번에 정리 (prompt `period_rollup`) |
| ppt/compose.py | 정리본 range가 ISO 주와 다르면 머리글 "기간 진행사항", 제목 "진행 현황 – 기간 내 진행" | 기간 보고를 주간업무 양식으로 |
| ppt/compose.py | 배경·목적이 비면 "- 배경·목적 미입력" (원래 "- -. -") | 미입력 프로젝트 |
| pptgen.py | `generate_ppt` 를 `prepare_ppt`(구성·페이지 나누기) + 렌더로 분리, `prepared=` 인자 | 여러 과제를 한 파일로 합치기 |
| report/generate.py | `exec_fill()`(경영진 1장 요약 슬라이드 1장 내용) 분리, `generate_monthly(org=)` | 여러 과제 경영진 요약을 한 파일로, 화면에서 고른 조직명 |
| worklog.py | 표 노드를 "\| 칸 \| 칸 \|" 행 단위로, 간트 노드를 "[간트] 이름 (MM/DD~MM/DD, 진행 n%)" 로 AI 입력에 넣음 | 원래는 표가 칸 단위로 흩어지고 간트는 빠졌음 |
| worklog.py | 과제 시작·종료일이 없으면 일정 칸 "미정" (계산용 날짜는 마일스톤 계획일) | 원래는 스키마 오류로 생성 실패 |

`report_assets/config/` 변경: `people.json` 예시 사람 제거(이름은 Worklog export에서 옴), `worklog_mapping.json` 에 레코드 상태 `completed`·`cancelled` 추가.
`report_assets/prompts/period_rollup.*.txt` 는 `weekly_rollup.*.txt` 에서 '이번 주' 표현만 '기간'으로 바꾼 새 파일이다.
