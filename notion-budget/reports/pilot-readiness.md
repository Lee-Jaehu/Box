# 코드북 정리와 새 시범 준비 — 2026-10-25

## 완료

- 열린 코딩 200건에서 `research/codebook.md` v1.0-candidate를 정리했다.
- 문제·효용 코드 C01~C19 + 기타 C99, 관련성, 포기 증거 유형, 단계, 실제 대안, Kano 후보의 정의와 포함/제외 예시를 기록했다.
- 기존 분류표 v0.2를 `codebook-legacy-v0.2.md`에 보존했다. 기존 제출 명령은 새 품질 게이트 준비 전 차단 상태다.
- `annotation.schema.json`은 로컬 구조 검사용 스키마다. 이것을 실제 API의 강제 출력으로 성공시켰다는 뜻은 아니다.
- 로컬 검증기는 원문에 없는 근거, 포기 증거 없는 원인 할당, 원인 목록에 없는 주원인, 근거 없는 단계 할당을 거부한다.
- 새 시범 200건을 `data/work/research-pilot-v1/`에 준비했다. 본문을 새로 라벨링하거나 모델로 전송하지 않았다.

| 출처 | 새 시범 |
|---|---:|
| Play | 67 |
| App Store | 67 |
| YouTube | 66 |
| 합계 | 200 |

seed 2026102503, 적격 후보 49,452건. 골드 100건·개발용 200건·기존 레거시 시범 200건 및 해당 중복 대표와 겹치는 ID는 없다.
시범 입력 SHA256: `c8f6c75945b280a1e5db9c1f3644c3b12274373c10a626bccd0d4d27bd3c8c48`.
골드 본문은 읽지 않았다. 이미 통과한 전체 비골드 대 골드 중복 감사 결과와 ID 분리를 재확인했다.

출력: `pilot_input.jsonl`, `pilot_ids.txt`, `pilot_review.csv`, `manifest.json`.
manifest는 사용한 입력 파일·코드북 해시와 제외 상태를 기록한다. 원문·새 시범 파일은 gitignore 경로에 보관하며 새로 공개 커밋하지 않았다.
균등 출처 표본이므로 이 분포를 전체 원인 비율로 해석하지 않는다.

검증: 자동 테스트 8개 통과. 새 시범을 임시 경로에서 재생성해 파일 해시가 동일함을 확인했고, 기존 출력 덮어쓰기 방지도 확인했다.

## 아직 실행하지 않은 것

ANTHROPIC_API_KEY가 없다. 지원되는 Haiku 5.5 모델 ID, Batch API·캐싱·JSON schema 동시 지원, 현행 가격은 미확인이다.
따라서 API 제출·요금 추정·실측 비용·품질 점수·Cohen κ는 아직 없다. 모델명을 추측해 호출하지 않는다.
독립 사람 골드 라벨도 없다. Codex가 개발에 쓴 라벨을 사람 골드로 재사용하지 않는다.
구조 검증을 통과해도 의미적 정확도나 평가 게이트가 통과된 것은 아니다.

## 재개 순서

1. 키는 채팅이 아닌 환경 설정에 등록한다. 존재와 실제 인증을 확인한다.
2. 공식 자료에서 사용 가능한 모델 ID·Batch/캐싱/강제 출력·가격을 확인한다.
3. 이 코드북과 별도 시범 200건으로만 실행하고 스키마/원문 근거 검증, 누락·실패율, 실제 토큰·캐시·요금을 보고한다.
4. 코드북 고정 후 독립 사람이 봉인된 100건을 라벨링한다. 골드의 모델 출력은 평가용 추론에만 사용한다.
5. 사전 고정 축의 κ와 불명률·희소 범주를 보고한다. κ < .7 또는 계산 불능이면 전량 중지한다.
6. 비골드만 BERTopic 탐색에 사용한다. 경쟁 조사·최종 원인 비율·결론은 실제 근거가 확보된 뒤 작성한다.

## 로컬 재현

```bash
cd /workspace/Box
/workspace/.box-env/research-venv/bin/pip install -r notion-budget/research/requirements-research.txt
PYTHONPYCACHEPREFIX=/workspace/.box-env/pycache /workspace/.box-env/research-venv/bin/python -m unittest discover -s notion-budget/research/tests -v
# 기존 시범 출력은 덮어쓰지 않는다. 재현은 새 경로로 실행한다.
PYTHONPYCACHEPREFIX=/workspace/.box-env/pycache /workspace/.box-env/research-venv/bin/python notion-budget/research/prepare_research_pilot.py --out /tmp/notion-research-pilot-replay
```
