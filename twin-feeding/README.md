# twin-feeding: 쌍둥이 수유 분업 도구

엄마는 젖 비우기(직수·유축)에만 집중하고, 나머지는 아빠가 맡도록 돕는 도구입니다.
2026-11-06 출생 쌍둥이: 딸은 집에서 직수, 아들은 NICU에서 엄마 유축모유.

| 경로 | 내용 |
|---|---|
| `docs/plan.md` | 설계서: 수유 계획 모델·배분 규칙, 분업·교대표, 데이터 구조, 위험 신호 기준표, 의료진 질문 목록, 검증 계획, 1차 출처 |
| `app/index.html` | 앱 (빌드 결과, Claude 아티팩트로 게시. 공유 DB로 두 폰 동기화, DB가 없으면 이 기기 저장) |
| `app/src/` | 앱 소스: `shell.html`(CSS·마크업), `icons.svg.html`(아이콘·아기 얼굴), `logic.js`(계산), `ui.js`(화면). `node twin-feeding/app/build.js`로 `index.html` 생성 |
| `forms/daily-log.pdf` | 오늘부터 쓰는 종이 기록지 (A4 가로 2쪽: 24시간 기록 / 모유 재고·NICU 배송·체중) |
| `tests/logic.test.js` | 계산 로직 테스트: `node twin-feeding/tests/logic.test.js` |

계산 로직(배분 규칙, 24시간 통계, 보관 기한, 연락 기준)은 `app/src/logic.js`에 있고, 테스트는 빌드된 `index.html`의 `LOGIC START`–`LOGIC END` 블록을 떼어 내 검증합니다.
숫자 기준은 모두 기본값입니다. NICU·소아과 확인 뒤 앱 설정에서 바꿔 쓰세요.
