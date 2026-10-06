# Worklog 개발 단계·검증 기준

## 진행 상태 (2026-10-04 갱신)

범례: ✅ 구현·검증함 / 🟡 일부 / ⬜ 미구현 / ❓ 구현했으나 해당 환경에서 **미검증**. 검증 근거와 미실시 사유는 [10_VERIFICATION_REPORT.md](10_VERIFICATION_REPORT.md).

| 단계 | 상태 | 요약 |
|---|---|---|
| P0 | 🟡 | 에디터·간트·이미지·왕복·버전 고정 ✅ / **한글 IME 실제 조합 ❓**, 실제 Excel 붙여넣기 ❓, 표 병합·간트의 실제 마우스 조작 ❓ |
| P1 | ✅ | 단, embedded Python 패키징 ❓ (선택 로직만 검증) |
| P2 | 🟡 | 일지·성과·첨부·초안 ✅ / “프로젝트 최근 일지 참고” ⬜ (같은 날짜 다른 담당자 일지 읽기 전용 목록은 ✅) |
| P3 | ✅ | tracker 수정 revision 충돌은 토스트 안내만(일지 충돌 같은 전용 화면은 ⬜) |
| P4 | 🟡 | export·백업·복원·패키지 ✅ / 화면에서 bundle 다운로드 ⬜(API만), 조직·사용자 이름 변경 화면 ⬜(API는 ✅, 화면은 활성/비활성만) |
| P5 | 🟡 | 20명 부하 스크립트·측정·동시성 정합성 ✅(이 PC) / 실제 사내망 접속·한글 경로 전체 구동·Python 후보별 실행 ❓ |

### 다음 작업 (우선순위)
1. 운영 PC 에서 [11_WINDOWS_SMOKE.md](11_WINDOWS_SMOKE.md) 수행 — 특히 한글 IME, Excel 붙여넣기, 마우스 표/간트, 다른 PC 접속.
2. 극단 연타 부하에서 저장 p95 2.05~2.23s (목표 2s) — 필요 시 저장 경로 쿼리 수(약 21문장/저장) 축소. 현실적 부하(생각 시간 0~3s)는 p95 0.15s 이하.
3. “프로젝트 최근 일지 참고”, bundle 다운로드 UI, 조직·사용자 수정 화면, tracker 충돌 전용 화면.
4. embedded Python 배포본 구성·검증(`_pth`, site-packages, 네이티브 wheel).
5. 코드 분할(번들 826 kB / gzip 254 kB) — 사내망에서는 문제 없으나 첫 로딩 개선 여지.

---

원래의 단계 정의(아래)는 완료 기준으로 유지한다.

## P0. 핵심 편집 시제품과 환경 조사

- 저장소 기존 코드/AGENTS 및 개발 환경 확인. 다른 프로젝트 코드 가정 금지.
- React/TypeScript/Vite, Tiptap 표/체크리스트, Frappe Gantt 최소 화면.
- 한글 IME 조합 중 입력·Enter·목록 종료, 카드 여러 개 전환 테스트.
- 마우스 표 생성/행열 편집/병합, 간트 날짜 이동/기간 조절, 이미지 설명 입력 구현.
- 문서 JSON serialize→reload 왕복, 이미지 사용처와 자유 gantt payload 확인.
- basic Excel 표 paste는 내용/행열 보존, 고급 서식 손실을 명시. 지원 안 되는 표 구조는 무음 삭제 금지.
- 정확한 라이브러리/Python/SQLite 버전·라이선스 고정, lockfiles와 third-party notices 작성.
- Windows 실행기 환경 선택을 unit-test 가능한 방식으로 분리. 실제 Windows 없으면 해당 검증을 미실시로 표시.

완료 기준: 작성/재열기에서 필수 정보 손실 없음; 지원 범위와 라이브러리 선택 근거 문서화. 임시 PNG만 저장하는 우회로 기능 완료 처리 금지.

## P1. 실행·데이터 기반

- FastAPI+빌드된 화면, config, SQLite/Alembic, UUID, 선택 actor, 상태 enum.
- 조직/사용자 CRUD·Excel/CSV preview/commit, 프로젝트/참여자/KPI/마일스톤, 일반 항목 자동 생성.
- 세션 작성자·조직 필터, 단발성 UI.
- 프로젝트/마일스톤 기간 검증, 공용 간트, 기준 일정 확정·이력.
- 수동 실행.bat Conda→embedded→venv; 초기 설정/오프라인 배포 설명.

완료 기준: 사번 없이 명단 등록, 팀 필터, 프로젝트 생성, 대표≠작성자, 마일스톤 빠른 생성. 오류 import 부분 적용 없음. 운영 Node 없이 빌드 화면 제공.

## P2. 일지·성과·첨부

- 프로젝트/작성자/날짜 고유키, 재진입 이어 쓰기, 여러 TASK·마일스톤, 날짜/순서/복사.
- 전체 저장, revision/Idempotency-Key, 브라우저 IndexedDB draft.
- 정량/정성 프리셋·KPI snapshot, 숫자 계산·회색 가이드.
- 이미지/문서 업로드, task binding·이미지 상세 설명 필수·정식 연결.
- Lesson Learned·메모·협업자, 프로젝트 최근 일지 참고.

완료 기준: 저장 중 입력 초안 손실 없음; 새로고침 복구; 다른 프로젝트/사용자 초안 혼합 없음; 이미지 캡션 누락은 필드 오류; 표/간트 포함 재열기 동일.

## P3. 트래커·삭제·충돌

- 일지 신규 To-Do/Issue 등록과 독립 현재 상태·원본 snapshot.
- 직접 등록, Issue→대응 To-Do, 완료/해결 결과와 선택 TASK 생성.
- 재개·재완료·이력; 종료 상태 자동 전파 금지.
- 휴지통/복원, 상위 삭제/하위 원래 삭제 상태 유지.
- 다른 수정 충돌 화면·내 초안 보존.

완료 기준: 중복 클릭/재시도에서 tracker/TASK 중복 없음. 완료 처리 중 log 충돌 시 tracker도 rollback. 과거 일지 삭제 후 tracker 유지. To-Do 완료가 Issue를 해결하지 않음.

## P4. JSON·백업·배포

- durable export jobs, 읽기 좋은 master/project/daily/trackers JSON.
- 같은 target coalescing·revision race·재시작 재시도·빈 날짜·삭제 상태 처리.
- export 상태·수동 rebuild·DB snapshot bundle·첨부 경로 manifest.
- SQLite backup API+참조 첨부 manifest, 최근 14개, 수동/첫 저장 예약, 복원.
- data/config 보존 업데이트, 빌드 산출물과 패키지 고정·실행 방법 제공.

완료 기준: JSON을 삭제해도 재생성 가능. DB 저장 직후 강제 종료 후 JSON 재개. backup restore 후 DB/첨부 일치. 실패한 백업이 정상 백업을 삭제하지 않음.

## P5. MVP 통합 검증

약 20명 세션의 조회/작성/저장/트래커 혼합 및 순간 저장 요청 테스트. 테스트는 CLI 부하 도구 또는 pytest/httpx로 재현 가능하게 구성. 운영 PC 성능 미상이며 아래 수치는 초기 합격 제안이지 사전 성능 보장이 아니다.

- 일반 텍스트/표 일지 20명 혼합 시 저장 p95 2초 이내 목표(첨부 업로드/대용량 import 제외).
- 20건 동시 저장에서 사용자 데이터 유실·중복 0. 충돌은 명확한 409로 분류.
- 일반 상태 JSON 지연 5초 이내 목표, exporter 실패 표시·재시도는 별도 검증.
- 첨부는 파일당 20MB 경계, Windows 백업/JSON 교체 실패 시 이전 정상 사본 유지.
- 실제 사내망 접속, 한글/공백 설치 경로, 사용할 Python 후보별 실행.

300명 부하 테스트·PostgreSQL·worker 확장은 별도 후속, MVP 합격 조건에 포함하지 않는다.

## 중요 테스트 목록

1. date timezone/자정 경계와 여러 사용자 로그 묶음.
2. 동일 일지 동시 생성 unique 충돌, 같은 log 수정 revision 충돌.
3. idempotency same payload 재전송 vs different payload 거부.
4. tracker 생성 clientEntryId 재전송; 기존 refs 누락이 tracker 삭제를 유발하지 않음.
5. tracker 완료+TASK 생성 fault injection rollback, reopen 후 독립 TASK 보존.
6. importer preview 이후 명단 변경 충돌, 사번 0/동명이인/오류 전량 차단.
7. editor JSON node/table spans/gantt dates/image caption roundtrip.
8. numeric before=0, 단위/기간 불일치, %와 %p, 감소 악화 부호.
9. exporter snapshot 중 갱신 도착, replace 직후 종료, empty logs, 삭제 프로젝트.
10. 휴지통 복원과 독립 삭제 자식, 첨부 재사용 참조·임시 정리.
11. DB/첨부 backup 복원, stale draft와 복원 세대 충돌.
12. Python fallback 선택(애플리케이션 오류 후 재시작 안 함), Windows 실제 smoke.

단순 화면 문구마다 테스트를 늘리지 말고 데이터 무결성·상태 전환·지원 UX의 핵심을 검증한다. pytest, httpx, Playwright 등은 개발 의존성 후보이며 실제 환경에 맞춰 최소로 선택한다.

## 작업 종료 보고 형식

구현한 기능 / 수정 파일 / 실제 실행한 검증과 결과 / 미실시 환경 검증 / 남은 작업 / 데이터 구조 변경 및 migration을 짧게 보고한다. 통과하지 않은 Windows/성능/라이브러리 기능을 완료로 표시하지 않는다.
