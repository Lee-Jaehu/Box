# API 키 등록 후 사전 점검 — 2026-10-25

## 확인한 것

- 현재 프로세스에 `ANTHROPIC_API_KEY`가 존재한다. 값은 출력·파일 저장·커밋하지 않았다.
- `GET https://api.anthropic.com/v1/models?limit=100` 인증에 성공했다.
- 모델 목록에 `claude-haiku-5-5` / Claude Haiku 5.5가 active로 표시됐다.
- 모델 메타데이터에서 Batch와 structured outputs 지원을 확인했다.
- 공식 Python SDK `anthropic==2.3.0`을 설치했고, 요청의 `output_config`와 캐시 설정용 파라미터를 확인했다.
- 새 시범 입력은 기존 해시와 일치하며 200건 그대로다. 골드 자료는 전송하지 않았다.

## 실제 실행을 막은 응답

시범 1건을 포함한 요청의 토큰 계산 사전 점검에서 HTTP 400 / `invalid_request_error`:

> Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.

키가 없거나 틀린 문제가 아니라 현재 API 계정/조직의 크레딧 부족 응답이다.
동일 요청을 반복하거나 다른 키를 요구하지 않았다. Batch 제출·분류 생성은 하지 않았다.
토큰 수·프롬프트 캐시 적중·서버의 스키마 수용 여부·실제 분류 품질·분류 요금은 아직 측정하지 못했다.
모델 메타데이터의 지원 표시와 실제 요청 성공은 구분한다.

공식 가격·캐싱 문서와 공개 가격 페이지도 HTTP 403으로 응답했다. 현행 단가를 추정해 비용으로 보고하지 않는다.
이 문서 접근 실패를 해결하려고 프록시나 TLS 검증을 우회하지 않았다.

## 사용자가 할 일과 재개

Anthropic Console의 **Plans & Billing**에서 해당 API 조직의 크레딧을 충전하거나 결제 상태를 확인한다.
Claude 채팅 구독의 상태와 별개로 이 키가 속한 API 조직에 사용 가능한 잔액이 필요하다.
충전 후 알려주면 토큰 계산부터 다시 확인하고, 통과하면 새 시범 200건만 Batch로 제출한다.
실행 전 가격 확인이 계속 불가능하면 토큰 사용량과 금액 미확인을 명확히 구분한다.
전량 분류는 시범 비용·품질 보고와 독립 골드 평가 이후에만 진행한다.

현재 상태: **시범 미제출 / 잔액 문제로 중단**. 원본 재수집·표본 재추출은 필요 없다.
