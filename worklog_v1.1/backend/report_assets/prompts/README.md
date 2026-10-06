# EXAONE 프롬프트 (시연용 v0.7)

> v0.7 (2026-10-06): 팀장 요약 페이지용 `project_summary` 추가 (과제 1건 → 배경·진행·이슈·잘한점·계획 요약 JSON, 신규 색은 Rule).
> [Worklog 통합] 주간·기간 보고 모두 사용: `{{period_label}}`(이번 주 / 보고 기간), `{{prev_label}}`(지난주까지 / 보고 기간 이전까지). 기간 보고의 정리 프롬프트는 `period_rollup`(weekly_rollup의 '이번 주' → '기간').

> v0.6 (2026-10-04): WorkLog 연동. weekly_rollup의 milestone_updates 지시를 변수 {{milestone_policy}}로 (WorkLog 관리 과제는 항상 []).
>
> v0.5 (2026-10-04): 문장 40~60자로 늘림, 진행 현황·이슈·누적 요약 문장 끝에 진행 날짜 "(MM/DD)" 표시 (메모 본문 날짜, 없으면 작성일).
>
> v0.4 (2026-10-04): 그룹장 보고용 경어체("~했습니다/~입니다") 종결, 한 항목 30~60자(함축 금지)로 변경. fit_to_budget에 min_chars 변수 추가.
>
> v0.3 (2026-10-03): cumulative_update의 max_items를 PPT 첫 장에 남는 줄 수로 정하고, 고정 사실의 핵심 수치를 items에 포함하도록 규칙 추가.

| prompt_id | 파일 | 언제 호출 | 결과 저장 |
|---|---|---|---|
| `weekly_rollup` | weekly_rollup.system.txt / .user.txt | 주간 마감, 과제마다 1회 | data/derived/weekly/{project_id}/{week}.json |
| `cumulative_update` | cumulative_update.system.txt / .user.txt | weekly_rollup 직후, 과제마다 1회 | data/derived/cumulative/{project_id}/{week}.json |
| `fit_to_budget` | fit_to_budget.system.txt / .user.txt | PPT 생성 전 분량 검사에서 칸이 넘칠 때만 | (저장 안 함, PPT 생성에 바로 사용) |
| `project_summary` | project_summary.system.txt / .user.txt | 보고자료 '팀장 요약 페이지 포함' 시 과제마다 1회 (같은 입력이면 저장된 응답 재사용) | 작업공간 data/derived/summary/{project_id}/{주차 또는 기간}.json |

- 모든 system 파일의 `{{common_rules}}` 자리에 `common_rules.txt` 내용을 넣는다.
- 호출 설정: temperature 0.1, 응답은 JSON만. 앞뒤 ```json 표시는 제거 후 파싱.
- 파싱 실패 시 1회 재요청: "직전 응답이 JSON 형식이 아닙니다. 같은 내용을 JSON으로만 다시 출력하세요."
- 결과 JSON의 `ai.prompt_id`, `ai.prompt_version`(v0.6)을 함께 저장한다.

## 변수

### weekly_rollup
| 변수 | 내용 | 예시 |
|---|---|---|
| week_label | 주차 표시 | W39 |
| budget_progress / budget_next_plan / budget_issues | 칸별 최대 항목 수 | 7 / 3 / 2 |
| project_id, project_name | 기준정보 | P-ASM-001, ESWA 재료교체 불량 개선 |
| range_from, range_to | 주 시작·끝 (월~일) | 2026-09-21, 2026-09-27 |
| milestone_policy | milestone_updates 작성 지시 (WorkLog 관리 과제는 "항상 []") | |
| milestone_lines | 마일스톤 한 줄씩 | `- M6-3 | 수평전개 | 적용 범위: Normal·조립 | Baseline 2026-09-25 | 계획 2026-09-25 | 상태 진행` |
| prev_weekly_lines | 지난주 주간 정리본 항목 (없으면 "없음") | `- [진행] ...` |
| daily_blocks | 이번 주 메모 원문 (아래 형식, 날짜순) | |

daily_blocks 형식:
```
- 기록 ID: D-260922-ljh-01 (2026-09-22, ljh, 카테고리 DATA)
  본문: (raw_text 그대로)
  표 [재료교체 위치 불량률 적용 전·후]
    구분 | 적용 전(%) | 적용 후(%)
    ESWA MEB | 0.171 | 0.144
    ESMI1 #2-2,3 | 0.367 | 0.23
```

### cumulative_update
| 변수 | 내용 |
|---|---|
| max_items | 누적 요약 최대 항목 수 (기본 7, PPT 첫 장에 남는 줄 수가 더 적으면 그 값, 최소 3) |
| background, purpose | 기준정보 배경·목적 |
| completed_milestones | 상태=완료인 마일스톤 "이름(완료일)" 목록 |
| prev_items, pinned_facts | 지난주 누적 요약 파일의 items, pinned_facts (첫 주면 "없음") |
| weekly_lines | 이번 주 weekly_rollup 결과의 progress, issues |

### fit_to_budget
| 변수 | 내용 |
|---|---|
| slot_name | 칸 이름 (예: progress) |
| max_items, max_chars, min_chars | 칸 한도 (항목 수, 문장 60자·40자) |
| item_lines | `- (D-260922-ljh-01) 문장` 형식 목록 |

### project_summary (팀장 요약 페이지)
공통 규칙(common_rules.txt)을 쓰지 않는다: 요약 페이지는 한 항목이 최대 2줄(40~100자), 날짜는 실제 작성본처럼 `.(9/30)`.
| 변수 | 내용 |
|---|---|
| max_lines | 이 과제에 줄 수 있는 줄 수 = (11pt 한 장 줄 수 − 과제 수×2) ÷ 과제 수, 5~12 |
| line_chars | 한 줄 글자 수 (LG스마트체 11pt, pjt_header 폭 기준 약 70자) |
| background, purpose, milestone_lines | 기준정보 (마일스톤은 weekly와 같은 형식) |
| cumulative_lines | **지난주**(기간 보고는 시작일 직전 주) 누적 요약 items (기존 → 검정, 합쳐서 짧게) |
| weekly_lines | 이번 주 주간 정리본 진행·계획·이슈 |
| daily_blocks | 이번 주 업무 기록 원문 (이슈·잘한점 근거, WorkLog 성과·배운 점 포함) |
| week_label, range_from, range_to | 주차(W40) 또는 기간(9/1~9/30) 표시 |
| period_label, prev_label | "이번 주"/"지난주까지" 또는 "보고 기간"/"보고 기간 이전까지" |

출력: `{"items": [{"category": "background|progress|issue|good|plan", "text", "source_ids", "details": [{"text", "source_ids"}]}]}`
- `new`(파랑)는 AI가 쓰지 않는다. source_ids에 이번 주 기록 ID가 있으면 Rule이 신규로 표시한다 (배경은 항상 검정).

## mock 응답
- 파일명: `mock_responses/{prompt_id}__{project_id}__{week}.json`
- 개발 환경(외부 PC)에서는 EXAONE에 접속할 수 없으므로 mock 모드가 이 파일을 응답으로 돌려준다.
- 현재 들어 있는 것: P-ASM-001 / 2026-W39 의 weekly_rollup, cumulative_update 기대 출력
