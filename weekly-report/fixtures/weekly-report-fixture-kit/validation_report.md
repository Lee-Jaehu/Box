# 예시 JSON 검증 결과

소스: /workspace/scratch/868a5560f4f1/repo/weekly-report
검증 환경: Python 3.12.14

모든 업무 내용은 합성 데이터. mock 실행은 AI 요약 품질이나 사내 API 연결을 검증하지 않음.

| 검사 | 결과 | 비고 |
|---|---|---|
| P-APC-101 Daily 필터 | PASS |  |
| P-APC-101 스키마 및 mock 실행 | PASS |  |
| P-APC-101 템플릿 누락 감지 | PASS | 실제 PPT 생성 및 시각 검증은 BLOCKED |
| P-ROL-102 Daily 필터 | PASS |  |
| P-ROL-102 스키마 및 mock 실행 | PASS |  |
| 일정 변경 overlay와 baseline 보존 | PASS |  |
| 완료 하위행 접기 | PASS |  |
| 접기 불가능한 12행의 초과 대응 | FAIL | 현재 12행 그대로 반환. PPT 생성기는 표 행 수만큼 잘라서 사용함. |
| P-ROL-102 템플릿 누락 감지 | PASS | 실제 PPT 생성 및 시각 검증은 BLOCKED |
| P-INV-103 Daily 필터 | PASS |  |
| P-INV-103 스키마 및 mock 실행 | PASS |  |
| P-INV-103 템플릿 누락 감지 | PASS | 실제 PPT 생성 및 시각 검증은 BLOCKED |
| P-SYS-104 Daily 필터 | PASS |  |
| P-SYS-104 스키마 및 mock 실행 | PASS |  |
| P-SYS-104 템플릿 누락 감지 | PASS | 실제 PPT 생성 및 시각 검증은 BLOCKED |
| P-DAT-105 Daily 필터 | PASS |  |
| P-DAT-105 스키마 및 mock 실행 | PASS |  |
| P-DAT-105 템플릿 누락 감지 | PASS | 실제 PPT 생성 및 시각 검증은 BLOCKED |
| 재실행 revision 증가 | PASS | 현재 재실행해도 revision=1 |
| 메모 없는 주 AI 호출 생략 | PASS |  |
| 이전 pinned_facts 누락 방지 | FAIL | mock이 이전 고정 사실을 반환하지 않으면 코드에서도 보존하지 않음 |
| 입력에 없는 4 수치 검출 | FAIL | 현재 숫자 4와 39는 예외 처리되어 누락됨 |
| 미존재 source ID 검출 | PASS |  |
| 원본 master/raw 보존 | PASS |  |

## 코드 검토로 확인한 추가 미구현 사항
- 지난주 weekly 입력이 항상 없음으로 전달됨.
- fit_to_budget 호출과 계속 슬라이드 생성이 구현되지 않음.
- 한글 LG Smart Regular의 ea 글꼴 설정이 구현되지 않음.
- cumulative 출력의 수치·근거에 대한 의미 검증 없음.
- 여러 과제를 같은 out-root로 실행하면 validation_{week}.txt가 덮어써짐.
- OPS 실적형은 저장 스키마와 생성 경로가 준비되지 않아 이번 5종에서 제외.

실제 PPT 검증은 공식 템플릿 추가 후 진행해야 함.
