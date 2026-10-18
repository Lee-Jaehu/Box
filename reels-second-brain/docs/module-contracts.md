# 1단계 미디어 모듈 입출력 계약

워커(`src/rsb/worker.py`)가 아래 함수만 호출한다. 타입은 `src/rsb/media/types.py`.
모든 함수는 예외를 던지지 않고 결과 객체의 status/error로 실패를 알린다(프로그래밍 오류 제외).

| 모듈 | 함수 | 결과 |
| --- | --- | --- |
| `rsb.media.fetch` | `fetch_video(url: str, dest_dir: Path, limits: Limits = Limits()) -> FetchResult` | URL이 영상 파일(Content-Type video/*)이면 직접 받고, 아니면 yt-dlp. `dest_dir` 안에 파일 1개 생성 |
| `rsb.media.fetch` | `check_public_url(url: str) -> None` | http/https가 아니거나 사설·루프백·링크로컬·멀티캐스트·예약 주소로 풀리면 `BlockedURLError` |
| `rsb.media.frames` | `sample_frames(video_path: Path, out_dir: Path, limits: Limits = Limits()) -> list[Frame]` | 장면 전환 또는 1초 간격 → 중복 제거 → 최대 `limits.max_frames`장 |
| `rsb.media.ocr` | `extract_screen_text(video_path: Path, reader: VisionReader, work_dir: Path, limits: Limits = Limits()) -> ExtractionResult` | medium="screen", segments=프레임 시각별 텍스트(연속 동일 텍스트는 합침). 글자 없으면 status="empty" |
| `rsb.media.transcribe` | `extract_speech(video_path: Path, transcriber: Transcriber, work_dir: Path, limits: Limits = Limits()) -> ExtractionResult` | medium="audio", ffmpeg로 16kHz mono 오디오 분리 후 전사. 오디오 트랙·발화 없으면 status="empty" |

백엔드 구현(환경변수로 선택, 키는 환경변수로만):

- `rsb.media.ocr.OpenAIVisionReader` — `OPENAI_API_KEY`, `RSB_VISION_MODEL`
- `rsb.media.transcribe.OpenAIWhisperTranscriber` — `OPENAI_API_KEY`, `RSB_WHISPER_MODEL`(기본 whisper-1)
- `rsb.media.transcribe.FasterWhisperTranscriber` — 선택 의존성 `local-whisper`

`extractor_version`은 `"<모듈>@<버전>+<백엔드 version>"` 형식으로 채운다(재처리 추적, PRD 10장).
