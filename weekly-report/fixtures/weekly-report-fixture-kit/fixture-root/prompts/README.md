# EXAONE 프롬프트 (시연용 v0.2)

| prompt_id | 파일 | 언제 호출 | 결과 저장 |
|---|---|---|---|
| `weekly_rollup` | weekly_rollup.system.txt / .user.txt | 주간 마감, 과제마다 1회 | data/derived/weekly/{project_id}/{week}.json |
| `cumulative_update` | cumulative_update.system.txt / .user.txt | weekly_rollup 직후, 과제마다 1회 | data/derived/cumulative/{project_id}/{week}.json |
| `fit_to_budget` | fit_to_budget.system.txt / .user.txt | PPT 생성 전 분량 검사에서 칸이 넘칠 때만 | (저장 안 함, PPT 생성에 바로 사용) |

- 모든 system 파일의 `{{common_rules}}` 자리에 `common_rules.txt` 내용을 넣는다.
- 호출 설정: temperature 0.1, 응답은 JSON만. 앞뒤 ```json 표시는 제거 후 파싱.
- 파싱 실패 시 1회 재요청: "직전 응답이 JSON 형식이 아닙니다. 같은 내용을 JSON으로만 다시 출력하세요."
- 결과 JSON의 `ai.prompt_id`, `ai.prompt_version`(v0.2)을 함께 저장한다.

## 변수

### weekly_rollup
| 변수 | 내용 | 예시 |
|---|---|---|
| week_label | 주차 표시 | W39 |
| budget_progress / budget_next_plan / budget_issues | 칸별 최대 항목 수 | 7 / 3 / 2 |
| project_id, project_name | 기준정보 | P-ASM-001, ESWA 재료교체 불량 개선 |
| range_from, range_to | 주 시작·끝 (월~일) | 2026-09-21, 2026-09-27 |
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
| max_items | 누적 요약 최대 항목 수 (기본 7) |
| background, purpose | 기준정보 배경·목적 |
| completed_milestones | 상태=완료인 마일스톤 "이름(완료일)" 목록 |
| prev_items, pinned_facts | 지난주 누적 요약 파일의 items, pinned_facts (첫 주면 "없음") |
| weekly_lines | 이번 주 weekly_rollup 결과의 progress, issues |

### fit_to_budget
| 변수 | 내용 |
|---|---|
| slot_name | 칸 이름 (예: progress) |
| max_items, max_chars | 칸 한도 |
| item_lines | `- (D-260922-ljh-01) 문장` 형식 목록 |

## mock 응답
- 파일명: `mock_responses/{prompt_id}__{project_id}__{week}.json`
- 개발 환경(외부 PC)에서는 EXAONE에 접속할 수 없으므로 mock 모드가 이 파일을 응답으로 돌려준다.
- 현재 들어 있는 것: P-ASM-001 / 2026-W39 의 weekly_rollup, cumulative_update 기대 출력

