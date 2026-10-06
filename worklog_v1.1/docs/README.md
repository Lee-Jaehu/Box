# Worklog — Codex Cold-start 문서 묶음

설계 기준일: 2026-10-04 (Asia/Seoul) · 문서 버전: 1.0

## 현재 상태

> **2026-10-04 업데이트:** 이 설계를 바탕으로 P0~P4 대부분이 구현되었다. 실행 방법·고정 버전·구현/미구현 목록은 저장소 루트 [README.md](../README.md), 실제로 확인한 것과 확인하지 못한 것은 [10_VERIFICATION_REPORT.md](10_VERIFICATION_REPORT.md), 운영 PC 확인 절차는 [11_WINDOWS_SMOKE.md](11_WINDOWS_SMOKE.md) 를 본다. 아래 문서 본문(01~06)은 설계 기준이며, 구현 중 확정·조정한 내용은 각 문서 끝의 “구현 반영” 절과 [08_DECISIONS.md](08_DECISIONS.md) 에 있다.

사용자와 요구사항·UX·저장 원칙을 협의한 **신규 프로젝트 설계 인계본**으로 시작했다. 이 묶음의 JSON은 합성 예시이지 실제 사용자 데이터가 아니다.

개인 Windows PC에서 수동 실행하는 사내 업무일지 서비스다. MVP 동시 작성 목표는 약 20명이다. 프로젝트·마일스톤 기준정보를 재사용하고, 사용자는 매일 수행한 일을 편하게 작성한다. SQLite를 원본으로 쓰고 프로젝트/날짜별 읽기 쉬운 JSON을 자동 생성한다. 후속 요약 에이전트·PPT Generator는 별도 단계다.

## 바로 이어서 개발하는 방법

1. 이 폴더를 신규 Worklog 저장소의 `docs/` 아래 복사하거나 현재 작업 폴더로 제공한다.
2. 개발 담당자에게 `09_PROMPT.md` 전체를 전달한다.
3. Codex는 이 README → 백서 → UX → 아키텍처 → 데이터/API → 운영 → 개발계획/결정원장을 읽는다.
4. 코드가 이미 있다면 현황과 차이를 먼저 조사한다. 없다면 `07_DEVELOPMENT_PLAN.md`의 P0부터 구현한다.
5. 문서의 기존 합의를 재질문하지 않는다. 구현 선택은 제안 기본값으로 진행하고, 중요한 제품 변경·실제 환경 차이만 질문한다.

## 파일 안내

| 문서 | 책임 |
|---|---|
| [01_WHITEPAPER.md](01_WHITEPAPER.md) | 목적·MVP 범위·제품 원칙 |
| [02_UX_SPEC.md](02_UX_SPEC.md) | 사용자 설정, 기준정보, 일지, 트래커, 성과·편집 UX |
| [03_ARCHITECTURE.md](03_ARCHITECTURE.md) | 기술 스택·트랜잭션·내보내기·계층 구성 |
| [04_DATA_MODEL.md](04_DATA_MODEL.md) | 논리 테이블·필드·스냅샷·문서 JSON 계약 |
| [05_API_SPEC.md](05_API_SPEC.md) | 제안 REST 계약·에러·동시 수정·멱등성 |
| [06_STORAGE_OPERATIONS.md](06_STORAGE_OPERATIONS.md) | 폴더·JSON·첨부·수동 실행·가져오기·백업 |
| [07_DEVELOPMENT_PLAN.md](07_DEVELOPMENT_PLAN.md) | 단계별 구현과 완료 기준·검증 |
| [08_DECISIONS.md](08_DECISIONS.md) | 확정 사항·철회된 안·구현 기본값·남은 검증 |
| [09_PROMPT.md](09_PROMPT.md) | 복사해 사용할 개발 시작 지시 |
| [10_VERIFICATION_REPORT.md](10_VERIFICATION_REPORT.md) | 구현·검증 결과, 발견한 결함, 미실시 항목 |
| [11_WINDOWS_SMOKE.md](11_WINDOWS_SMOKE.md) | 운영 PC 스모크 체크리스트 |
| [examples/daily.example.json](examples/daily.example.json) | 프로젝트/날짜 JSON 내보내기 예시 |
| [examples/project.example.json](examples/project.example.json) | 기준정보·마일스톤·KPI 내보내기 예시 |

## 문서 해석 규칙

- **확정:** 사용자가 수락한 요구사항이다. 구현 편의를 이유로 제거하거나 반대로 되돌리지 않는다.
- **구현 기본값:** 합의를 구체화한 설계자의 제안이다. 구현 검증 후 근거와 함께 조정하고 결정원장을 갱신한다.
- **검증 필요:** 아직 동작·호환성·성능을 확인하지 않았다는 뜻이다. 완료됐다고 보고하지 않는다.
- 충돌은 사용자 최신 지시 → `08_DECISIONS.md`의 확정 사항 → 백서 → UX → 상세 설계 순으로 판단한다. 기술 기본값이 제품 합의를 덮어쓰지 않는다.
- 파일명·필드명·API 경로는 이 인계본의 구현 기본값이며, 초기 구현에서 정합성을 유지하며 조정할 수 있다.

## 주요 제약

- 독립 신규 Worklog만 개발한다. 기존 다른 업무 시스템의 코드·도메인·자산에 의존하지 않는다.
- 로그인·SSO·권한 없음. 선택 작성자는 자기신고 정보이며 검증된 신원이 아니다.
- 사번 선택, 내부 UUID 필수. 프로젝트 담당 팀은 하나다.
- 일지 고유 단위: 프로젝트 + 작성자 + 업무 날짜. TASK는 일지마다 새로 작성, 별도 상태 없음.
- 수동 `실행.bat`. Python 탐색은 Conda → embedded Python → `.venv` 순서. 자동 시작·서비스·자동 재시작 없음.
- 운영에 Node.js 불필요. 개발 시 화면 빌드에만 사용한다.
- SQLite 원본, JSON은 단방향 자동 사본. 사본 직접 편집 자동 반영 금지.
- 최대 300명 확장은 후속 검토다. MVP 인프라·합격 기준을 300명으로 키우지 않는다.

## 코드 생성 후 README 갱신

완료: 실제 설치·실행 명령, 고정 버전, 테스트 결과, URL, 환경변수, 구현/미구현 목록은 저장소 루트 [README.md](../README.md) 와 [10_VERIFICATION_REPORT.md](10_VERIFICATION_REPORT.md) 에 기록했다. 새 기능을 추가하면 두 문서와 결정 원장을 함께 갱신하고, 검증하지 못한 항목은 완료로 표시하지 않는다.
