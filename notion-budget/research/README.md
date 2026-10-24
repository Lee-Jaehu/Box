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
python classify.py submit --tag pilot --ids ../data/work/pilot_ids.txt   # (권장) 200건 시범으로 실제 비용·품질 확인
python classify.py collect --tag pilot
python classify.py submit --tag primary --model claude-opus-5-5
python classify.py collect --tag primary
python classify.py sample --tag primary                      # kappa용 100건(관련 70 + 무관 30)
python classify.py submit --tag second --model claude-sonnet-5-5 --ids ../data/work/kappa_ids.txt
python classify.py collect --tag second
python classify.py kappa --a primary --b second              # relevant·주 주제·주 극성 모두 0.7 이상이어야 통과
```

## 새 세션에서 이어서 하기 (API 키 등록 후)
환경 시크릿은 새 세션부터 적용됩니다. 이전 세션 컨테이너의 `data/`는 남지 않습니다.
1. 환경 변수 `ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`이 있는지 확인합니다.
2. 수집을 다시 실행합니다(`collect_play.py`, `collect_appstore.py`, `collect_youtube.py`, `collect_naver_blog.py`). 분석 기준 스냅샷은 이 재수집본이고, 2026-10-24 수집본은 사용자가 Drive에 보관합니다.
3. `classify.py`를 위 순서대로 실행합니다(시범 → 전체 → kappa).

## 원본 데이터 보관 원칙
- 원본은 `notion-budget/data/raw/{source}/{key}_{YYYYMMDD}.csv`에 저장하고 **수정하지 않습니다.**
- `data/`는 `.gitignore` 대상입니다. 이 저장소는 공개 저장소이고, 원본에는 작성자 닉네임이 들어 있으므로 **커밋하지 않습니다.**
- 분석용 사본에서는 닉네임 열을 지웁니다.
