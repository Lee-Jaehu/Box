# 데모: Daily 메모 → 주간 정리 → PPT

저장소 예시(P-ASM-001, W39)에 이어지는 **W40 Daily 메모**로 전체 흐름을 직접 돌려 보는 데모다.
저장소의 `data/` 예시는 바꾸지 않는다. 실행할 때마다 임시 root를 만들어 데모 메모를 더한다.

```bash
cd weekly-report
python demo/run_demo.py demo/w40 P-ASM-001 2026-W40
```

## w40 구성

| 경로 | 내용 |
|---|---|
| `w40/raw/daily/…` | 9/28~10/2 Daily 7건. 그중 2건은 걸러져야 하는 메모(개인 메모 1, 삭제 메모 1) |
| `w40/prompts_sent/` | 파이프라인이 EXAONE에 보낼 프롬프트 전문 (실행 시 생성) |
| `w40/mock_responses/` | EXAONE 대신 쓴 응답. **EXAONE API를 받기 전이라 Claude가 위 프롬프트의 규칙대로 작성** |
| `w40/out/data/derived/…` | 생성된 weekly·cumulative JSON |
| `w40/out/output/…` | PPT, 의미 검증 보고서, PPT 재검사 보고서, LG스마트체 미리보기 PNG |

## 메모를 바꿔 보려면

1. `w40/raw/daily/`의 메모를 고치거나 추가한다 (형식은 `schemas/daily.schema.json`).
2. `w40/mock_responses/`의 해당 파일을 지우고 실행하면, 새 프롬프트를 `prompts_sent/`에 남기고 "응답 대기"로 멈춘다.
3. 그 프롬프트에 대한 응답 JSON을 `mock_responses/`에 넣는다(EXAONE 연결 전에는 Claude에게 요청) → 다시 실행한다.

다른 주차는 `demo/w41/`처럼 폴더를 만들어 같은 방식으로 쓴다.
이전 주 결과가 필요하면 그 주차의 `out/data/derived`를 다음 데모 폴더에서 참조하도록 확장하면 된다.
