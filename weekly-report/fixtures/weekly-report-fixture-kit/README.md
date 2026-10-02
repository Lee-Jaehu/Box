# 주간보고 합성 데이터 검증 패키지

검증한 저장소: Lee-Jaehu/Box
기준 커밋: 76be2a7de325007b470ec753ce110e158f2cc2c9
Python 3.12. 시연 목표 Python 3.11에서는 별도 확인 필요.

## 내용
- fixture-root/data/master/projects: 서로 다른 유형의 합성 과제 5건
- fixture-root/data/raw/daily: 과제별 정상 1건과 private/삭제/다른 주 제외 메모 3건, 총 20건
- fixture-root/data/derived/cumulative: W38 초기 누적 5건
- fixture-root/prompts/mock_responses: W39 주간/누적 mock 응답 10건
- fixture-root/config, schemas, prompts: 기준 커밋에서 가져온 설정과 계약
- results: 실제 코드의 mock 실행 결과. 프로젝트별 디렉터리로 보고서 충돌 방지
- manifest.json: 유형별 입력과 기대 선택 ID
- verify_fixtures.py: 재현 가능한 검증 스크립트
- validation_results.json / validation_report.md: 24개 검사 중 21개 통과, 3개 실패

## 재실행
저장소 코드는 이 패키지에 포함하지 않았습니다. Box를 별도로 체크아웃하세요.
현재 저장소 requirements와 pytest를 설치한 환경에서 아래 명령을 실행합니다.

```bash
python verify_fixtures.py /absolute/path/to/Box/weekly-report
```

스크립트는 fixture-root를 임시 디렉터리에 복사하고 테스트합니다.
저장소 원본 파일을 수정하지 않으며, 패키지 내부 results와 보고서만 갱신합니다.
실패 사례는 FAIL로 보고서에 남깁니다. 스크립트 종료 코드는 검사 수행 완료만 의미합니다.

## 사례
1. P-APC-101 / TPL-APC: 자동보정 수치 비교
2. P-ROL-102 / TPL-ROLL: 일정 변경, 12행 마일스톤과 완료 하위행 접기
3. P-INV-103 / TPL-INV: 투자 심의
4. P-SYS-104 / TPL-SYS: 시스템 구축
5. P-DAT-105 / TPL-DATA: 수율 분석

모든 데이터는 합성이며 실제 투자·성과를 의미하지 않습니다.
mock 응답은 고정값이므로 AI의 실제 요약 정확도를 검증하지 않습니다.
정상 fixture에서는 구조와 데이터 전달을 확인합니다.
별도 경계 검사는 입력을 변형해 고정 사실 보존과 수치 검증 등의 결함을 확인합니다.
공식 PPT 템플릿과 사내 API는 포함하지 않았고, 실제 PPT 시각 검증은 차단 상태입니다.
운영·상시(TPL-OPS) 실적형은 현재 스키마/생성 경로 지원이 미비해 제외했습니다.

## 다음 Codex 요청
이 패키지의 validation_report.md와 verify_fixtures.py를 읽고
FAIL 3건을 수정해줘. 검증 조건이나 예시를 완화해서 통과시키지 마.
그다음 지난주 weekly 참조, 누적 출력 의미 검증, 과제별 검증 리포트 분리,
fit_to_budget와 최대 2장 계속 슬라이드 생성을 구현해줘.
공식 템플릿이 준비된 뒤 한글 ea 글꼴과 PPT 내용 누락·잘림을 검증해줘.
