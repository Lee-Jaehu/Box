# 주간업무 자동화 시연

Python 3.11 기반의 두 모듈입니다. `weekly`는 해당 ISO 주(월~일)의 Daily 원문과 표 값으로 weekly/cumulative JSON을 만들며, `pptgen`은 기준정보의 **메모리 복사본**에 주간 마일스톤 변경을 적용해 공식 v2 템플릿을 채웁니다. `data/master`, `data/raw`는 읽기만 하고 결과는 지정한 `data/derived`, `output`에 원자적으로 기록합니다.

## 설치와 P-ASM-001 / 2026-W39 실행

```bash
cd weekly-report
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 기존 예시를 덮어쓰지 않는 mock 실행
OUT=$(mktemp -d)
PYTHONPATH=. .venv/bin/python -m weekly_report weekly P-ASM-001 2026-W39 --out-root "$OUT"

# 전체 파이프라인(공식 템플릿이 추가된 뒤)
PYTHONPATH=. .venv/bin/python -m weekly_report pipeline P-ASM-001 2026-W39 --out-root "$OUT"
```

기본 AI 모드는 mock이며 파일명은 `prompts/mock_responses/{prompt_id}__{project_id}__{week}.json`입니다. `--mode live`는 `EXAONE_API_URL`, `EXAONE_API_KEY`를 읽습니다. 범용 Chat Completions 형태의 어댑터만 구현했으며 **실제 사내 API 계약/연결은 검증되지 않았습니다**. JSON 파싱은 안내 문구와 함께 한 번 재요청하고, HTTP/timeout 오류에는 키를 포함하지 않습니다.

`pptgen`은 기본적으로 `templates/주간업무PPT_Template_v2.pptx`를 요구합니다. 현재 그 파일과 완성 예시가 없으므로 PPT 생성은 필수 도형 목록을 포함한 오류로 중단됩니다. 저장소 루트의 `../주간업무PPT_Template.pptx`는 v2로 간주하거나 자동 대체하지 않습니다.

## 검증 정책

JSON Schema 구조 검증과 의미 검증을 분리합니다. 구조 오류는 derived 파일로 쓰지 않습니다. 구조가 맞는 AI payload는 저장하고, 잘못된 근거 ID·수치·마일스톤은 `output/validation_{week}.txt`에 경로와 이유를 남깁니다. `milestone_updates`의 null/없는 ID 및 필드별 잘못된 타입은 PPT에 적용하지 않습니다. Daily가 없으면 AI를 부르지 않고 `no_change=true`, 변경 없음 headline을 만들며 이전 누적을 유지합니다.

테스트는 `pytest -q`로 실행하며 `tmp_path`만 출력 위치로 사용합니다.

## 확인된 문서·예시 불일치와 결정

* `CLAUDE.md` 상단 최신 범위는 review/제안/Daily별 AI를 제외하지만 `INTERFACE_SPEC.md` 본문 흐름과 체크리스트에는 구 범위가 남아 있습니다. 상단의 최신 범위를 적용했습니다.
* 인터페이스 문서의 config 위치는 `data/master/codes`지만 실제 파일은 `config/`에 있습니다. 실제 구조를 읽되 기준정보처럼 수정하지 않습니다.
* `CLAUDE.md`는 PPT 결과를 `output/`으로 정하지만 인터페이스 트리는 `derived/ppt`입니다. 사용자 요구에 따라 `output/`을 사용합니다.
* mock/기존 W39 JSON은 prompt v0.1이나 prompt 문서는 v0.2입니다. 새 생성물은 실제 읽은 프롬프트 버전 v0.2로 기록합니다.
* 기존 W39 mock은 존재하지 않는 `CP-260922-001`을 source로 사용하고, 확정되지 않은 `ESMI1` 표기를 정상 코드처럼 출력합니다. payload를 임의 수정하지 않고 저장한 뒤 의미 검증 보고서에 표시합니다. `0.230`과 원문 표 값 `0.23`은 숫자로 동등하지만 표시 정밀도 차이는 검증 보고 대상입니다.
* 기존 cumulative에는 과거 항목의 근거가 프로젝트 ID뿐이라 원문 확인 사실과 이전 요약에서 승계된 사실을 완전히 구분할 수 없습니다. 승계 항목은 그대로 보존하며 검증됐다고 주장하지 않습니다.
* `plan_text`는 날짜/지연 일수 계산보다 우선 표시합니다. 날짜가 명시된 plan만 baseline과의 달력 일수 차이를 코드에서 계산합니다.
* 공식 v2 템플릿과 완성 예시가 모두 누락돼 색상·폰트·표 값·2장 출력의 통합 검증은 차단되어 있습니다. 템플릿 독립 로직과 누락/도형 검사 테스트는 완료했습니다.
