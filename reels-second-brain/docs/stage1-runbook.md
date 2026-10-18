# 1단계-B 실계정 연동 절차

1단계-A(코드·모의 테스트)는 끝났다. 아래는 재후의 계정 준비(PRD 12장) 후 진행한다.
결과 보고 시 '모의 테스트 통과'와 '실계정 연동 성공'을 구분한다.

## 1. 배포

- 이미지 하나(`Dockerfile`)로 두 프로세스를 띄운다.
  - 웹: 기본 CMD (마이그레이션 → uvicorn)
  - 워커: `python -m rsb.worker` (ffmpeg·yt-dlp 실행, `/data` 디스크 필요)
- 환경변수는 `.env.example` 목록을 호스팅 환경변수로 넣는다. 저장소·대화창에 값을 올리지 않는다.
- `RSB_TOKEN_KEY`는 Fernet 키로 생성한다(`.env.example` 주석).

## 2. Meta 웹훅

1. 앱 대시보드 웹훅 URL `https://<호스트>/webhook/instagram`, 검증 토큰 = `IG_VERIFY_TOKEN` → GET 검증 통과 확인.
2. `messages` 필드 구독.
3. 재후 본계정에서 세컨브레인 계정으로 아무 DM 1개 → 이 메시지는 허용 목록이 비어 있어 `ignored`로 저장된다.
4. `python -m rsb.cli senders`로 본계정 sender_id 확인 → `IG_ALLOWED_SENDER_IDS`에 넣고 재시작.
   (웹훅의 sender.id는 앱 범위 ID라 미리 알 수 없다.)

## 3. 릴스 5개 전송

- 서로 다른 제작자, 자막형·음성형을 섞는다.
- 하나는 같은 릴스를 두 번 보내 중복 처리(접수 기록만 추가)를 확인한다.
- `python -m rsb.cli status`로 릴스별 확보 방식(direct / yt-dlp)과 매체별 추출 상태를 본다.

### 확인할 [가설] (PRD 8.1)

| 항목 | 확인 방법 | 결과 |
| --- | --- | --- |
| 첨부 type이 `ig_reel`인가 | `webhook_events.payload` | |
| video id 필드 이름(`reel_video_id`?) | 〃 | |
| title이 전체 캡션인가 | 원본 캡션과 대조 | |
| url이 영상 파일인가(Content-Type video/*) | `reels.fetch_method` = direct / yt-dlp | |
| 재전달 시 같은 mid인가 | `webhook_events` 중복 여부 | |
| 답장 에코가 is_echo로 오는가 | 에코가 이벤트로 저장되지 않았는지 | |

페이로드 필드가 다르면 `src/rsb/instagram.py`의 `parse_entries`만 고친다. 실제 페이로드는 ID·URL을 가린 뒤 `tests/fixtures/real/`에 넣고 테스트를 추가한다.

## 4. 카카오

1. 브라우저에서 `https://<호스트>/oauth/kakao/login` → 첫 시도는 `KAKAO_ALLOWED_USER_ID=<id>` 안내와 함께 거부된다. 그 값을 환경변수에 넣고 재시작한 뒤 다시 로그인.
2. `curl -X POST -H "Authorization: Bearer $RSB_ADMIN_TOKEN" https://<호스트>/admin/kakao/test-send`
3. 실제 휴대폰에서 알림(소리·배너)이 오는지 기록 → D8 결정 근거.

## 5. 게이트 (PRD 9장)

- 5개 중 4개 이상 영상 확보·추출 성공 → PRD 갱신 후 2단계.
- 결과표를 이 문서 아래에 기록한다.
