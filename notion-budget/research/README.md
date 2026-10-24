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
NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python collect_naver_blog.py
```

## 원본 데이터 보관 원칙
- 원본은 `notion-budget/data/raw/{source}/{key}_{YYYYMMDD}.csv`에 저장하고 **수정하지 않습니다.**
- `data/`는 `.gitignore` 대상입니다. 이 저장소는 공개 저장소이고, 원본에는 작성자 닉네임이 들어 있으므로 **커밋하지 않습니다.**
- 분석용 사본에서는 닉네임 열을 지웁니다.
