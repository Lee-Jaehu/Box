# Phase 1 리서치: 리뷰·댓글 수집과 분류

## 파일
| 파일 | 역할 |
|---|---|
| `apps.json` | 대상 앱과 스토어 ID, YouTube·네이버 검색어 |
| `resolve_apps.py` | 스토어 ID가 맞는 앱인지 확인 |
| `collect_play.py` | Google Play 리뷰 (별점·날짜·버전·개발사 답변) |
| `collect_appstore.py` | App Store 리뷰 (공식 RSS, 앱당 최대 500건, 개발사 답변 없음) |
| `collect_youtube.py` | YouTube 댓글 (`YOUTUBE_API_KEY` 필요) |
| `collect_naver_blog.py` | 네이버 블로그 검색 결과 (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 필요, 본문 아닌 요약만) |
| `codebook.md` | 분류 기준표 |
| `jtbd-interview-guide.md` | 지인 인터뷰 질문지 |

## 실행
```bash
pip install google-play-scraper==1.2.7
python resolve_apps.py
python collect_play.py --max 5000
python collect_appstore.py
YOUTUBE_API_KEY=... python collect_youtube.py
NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python collect_naver_blog.py --fetch-body   # robots.txt 허용 시에만 본문 수집
```

## 분류 (`classify.py`)
```bash
pip install anthropic
python classify.py prepare                                   # 대상 추출 → data/work/items.jsonl
python classify.py pilot --n 200
python classify.py submit --tag pilot --model claude-haiku-5-5 --ids ../data/work/pilot_ids.txt   # 결정(10/24): Haiku 5.5로 200건 시범 → 비용·품질 보고 후 전체 진행 여부 결정
python classify.py collect --tag pilot
python classify.py submit --tag primary --model claude-haiku-5-5
python classify.py collect --tag primary
python classify.py sample --tag primary                      # kappa용 100건(관련 70 + 무관 30)
python classify.py submit --tag second --model claude-sonnet-5-5 --ids ../data/work/kappa_ids.txt
python classify.py collect --tag second
python classify.py kappa --a primary --b second              # relevant·주 주제·주 극성 모두 0.7 이상이어야 통과
```

## API 키 없이 분류하기 (2026-10-25 결정)
추가 비용을 쓰지 않기 위해 Batches API 대신 Claude Code 세션 안에서 분류합니다. 결과 파일 형식은 `collect`와 같아서 `sample`·`kappa`를 그대로 씁니다.
1. `prepare`, `pilot --n 200`을 실행하고, 시범 200건은 세션에서 직접 분류해 `labels_pilot.jsonl`로 저장합니다.
2. `sample --tag pilot`으로 kappa용 100건을 뽑고, 라벨 없이 원문만 담은 파일을 별도 에이전트(기준표와 원문만 읽음)가 분류해 `labels_second.jsonl`로 저장합니다. `kappa --a pilot --b second`로 게이트를 확인합니다.
3. `stratify`로 앱별 층화 표본(키워드 후보 230 + 비후보 20)과 층 가중치(`weights.jsonl`)를 만듭니다. 시범과 겹치는 건은 시범 라벨을 재사용하고, 나머지는 200건씩 나눠 에이전트들이 분류한 뒤 합쳐 `labels_primary.jsonl`로 저장합니다.
4. 집계할 때는 `weights.jsonl`의 가중치로 모집단 비율을 복원합니다.
5. Claude가 아닌 분류자로 교차 검증할 때는 kappa 표본과 기준표, `AGENTS.md` 지시문만 담은 폴더를 Codex CLI(`codex login --device-auth`로 ChatGPT 계정 로그인, `codex exec -s workspace-write -C <폴더>`)에 주고, Claude 라벨은 다른 폴더에서 채점합니다. 끝나면 `codex logout`으로 토큰을 지웁니다.

## 새 세션에서 이어서 하기 (API 키 등록 후)
환경 시크릿은 새 세션부터 적용됩니다. 이전 세션 컨테이너의 `data/`는 남지 않습니다.
1. 환경 변수 `ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`이 있는지 확인합니다.
2. 수집을 다시 실행합니다(`collect_play.py`, `collect_appstore.py`, `collect_youtube.py`, `collect_naver_blog.py`). 분석 기준 스냅샷은 이 재수집본이고, 2026-10-24 수집본은 사용자가 Drive에 보관합니다.
3. `classify.py`를 위 순서대로 실행합니다(시범 → 전체 → kappa).

## 원본 데이터 보관 원칙
- 원본은 `notion-budget/data/raw/{source}/{key}_{YYYYMMDD}.csv`에 저장하고 **수정하지 않습니다.**
- `data/`는 `.gitignore` 대상입니다. 이 저장소는 공개 저장소이고, 원본에는 작성자 닉네임이 들어 있으므로 **커밋하지 않습니다.**
- 분석용 사본에서는 닉네임 열을 지웁니다.
