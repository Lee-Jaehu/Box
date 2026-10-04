# 보고 자료 EXAONE 프롬프트 (설계 초안 r0.1)

> r0.1 (2026-10-04): 월간 종합 보고·경영진 1장 요약 초안. 장표모음집 분석 결과(docs/보고자료_양식_분석.md) 반영.
> 아직 렌더러에 연결하지 않았다. EXAONE 수동 시험용 예시는 docs/보고자료_예시/.

| prompt_id | 파일 | 출력 형식 | 변수 생성 |
|---|---|---|---|
| `report/report_monthly` | report_monthly.system.txt / .user.txt | schemas/report_monthly.schema.json | `report_vars.monthly_variables(root, project_ids, year, month, dirs)` |
| `report/report_exec_summary` | report_exec_summary.system.txt / .user.txt | schemas/report_exec_summary.schema.json | `report_vars.exec_variables(root, project_id, as_of_week, dirs)` |

- 두 system 파일의 `{{report_rules}}` 자리에 `report_common_rules.txt`를 넣는다 (`report_vars.render_report_prompt`).
- 문체: 헤드메시지·보고 배경 및 결론 = 경어체 완결문, 그 외 본문 = 개조식 (모음집 방식, 2026-10-04 결정).
- 표에 들어가는 값(상태·일정·지연일·KPI)은 Rule이 기준정보로 채운다. 입력의 "과제 목록 (코드가 표에 넣는 값)"은 AI 참고용이다.
- 응답 검사: `ai.read_payload`(JSON 추출·근거 ID 분리) → JSON Schema → `validate.check_item`(수치·날짜·근거) →
  `report_vars.report_style_problems`(분량·문체·강조 구절). 실패 시 1회 재요청 후 그 칸만 Rule 문장으로 대체(렌더러 단계).

## 변수

### report_monthly
| 변수 | 내용 |
|---|---|
| org, month_label, week_span | 보고 정보 (예: 제조DX그룹, ’26.10월, W40~W44) |
| project_lines | 과제별 한 줄: ID, 이름, 상태·건강도, 목표, 지연 단계(+n일, 코드 계산), KPI 기준→최신 |
| weekly_blocks | 그 달 주차별 주간 정리본 ([요약]/[진행]/[계획]/[이슈] + [근거: ID]) |
| cumulative_blocks | 과제별 최신 누적 요약 |
| head_max, comment_max, body_max, highlight_max_items, risk_max_items, request_max_items | 칸 분량 (`MONTHLY_BUDGET`) |

### report_exec_summary
| 변수 | 내용 |
|---|---|
| project_id, project_name, org, period, status, health, background, purpose | 기준정보 |
| kpi_lines | KPI 기준 → 최신 실적(기간), 목표 |
| milestone_lines | 마일스톤 (일정 변화 덧씌움 반영, 주간 프롬프트와 같은 형식) |
| as_of_week, cumulative_lines, pinned_lines | 최신 누적 요약·고정 사실 |
| weekly_blocks | 최근 4주 주간 정리본 |
| title_max, head_max, bc_items, bc_max, emphasis_max, subtitle_max, body_max, left_max_items, right_max_items | 칸 분량 (`EXEC_BUDGET`) |
