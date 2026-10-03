# 예시 JSON 검증 결과

소스: /home/user/Box/weekly-report
검증 환경: Python 3.11.15

모든 업무 내용은 합성 데이터. mock 실행은 AI 요약 품질이나 사내 API 연결을 검증하지 않음.

| 검사 | 결과 | 비고 |
|---|---|---|
| P-APC-101 Daily 필터 | PASS |  |
| P-APC-101 스키마 및 mock 실행 | PASS |  |
| P-APC-101 검증 보고서 과제별 분리 | PASS |  |
| P-APC-101 템플릿 누락 감지 | PASS |  |
| P-APC-101 PPT 생성·재검사(색·글꼴·표·장수) | PASS |  |
| P-ROL-102 Daily 필터 | PASS |  |
| P-ROL-102 스키마 및 mock 실행 | PASS |  |
| P-ROL-102 검증 보고서 과제별 분리 | PASS |  |
| 일정 변경 overlay와 baseline 보존 | PASS |  |
| 완료 하위행 접기 | PASS |  |
| 접기 불가능한 12행의 초과 대응 | PASS | 9행 + (계속) 장 3행 이월 |
| P-ROL-102 템플릿 누락 감지 | PASS |  |
| P-ROL-102 PPT 생성·재검사(색·글꼴·표·장수) | PASS |  |
| P-INV-103 Daily 필터 | PASS |  |
| P-INV-103 스키마 및 mock 실행 | PASS |  |
| P-INV-103 검증 보고서 과제별 분리 | PASS |  |
| P-INV-103 템플릿 누락 감지 | PASS |  |
| P-INV-103 PPT 생성·재검사(색·글꼴·표·장수) | PASS |  |
| P-SYS-104 Daily 필터 | PASS |  |
| P-SYS-104 스키마 및 mock 실행 | PASS |  |
| P-SYS-104 검증 보고서 과제별 분리 | PASS |  |
| P-SYS-104 템플릿 누락 감지 | PASS |  |
| P-SYS-104 PPT 생성·재검사(색·글꼴·표·장수) | PASS |  |
| P-DAT-105 Daily 필터 | PASS |  |
| P-DAT-105 스키마 및 mock 실행 | PASS |  |
| P-DAT-105 검증 보고서 과제별 분리 | PASS |  |
| P-DAT-105 템플릿 누락 감지 | PASS |  |
| P-DAT-105 PPT 생성·재검사(색·글꼴·표·장수) | PASS |  |
| 재실행 revision 증가 | PASS |  |
| 메모 없는 주 AI 호출 생략 | PASS |  |
| 이전 pinned_facts 누락 방지 | PASS |  |
| 입력에 없는 4 수치 검출 | PASS |  |
| 미존재 source ID 검출 | PASS |  |
| 원본 master/raw 보존 | PASS |  |

## 남은 제한
- mock 응답은 고정값이라 AI 요약 품질·사내 API 연결은 검증하지 않음.
- OPS 실적형은 저장 스키마와 생성 경로가 준비되지 않아 이번 5종에서 제외.
- 완성 예시 PPT(templates/주간업무_예시_조립자동보정팀_W39.pptx)가 없어 시각 기준 비교는 하지 않음.
