"""jobs 워커 (PRD 7장 1~2단계: 영상 확보 → 음성·화면·캡션 추출, 그리고 DM 답장).

상태는 각 작업의 성공·실패로 정한다. 모델 출력이 처리 완료를 선언하지 않는다.
실행: python -m rsb.worker
"""

from __future__ import annotations

import json
import logging
import shutil
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx
import psycopg

from . import db, instagram, jobs
from .config import Settings, get_settings
from .media.types import ExtractionResult, FetchResult, Limits, Transcriber, VisionReader

log = logging.getLogger(__name__)

REPLY_WINDOW = timedelta(hours=24)
CAPTION_VERSION = "caption@1"
# 다시 시도해도 결과가 같은 실패
PERMANENT_FETCH_ERRORS = ("blocked_url", "too_large")


class PermanentError(Exception):
    pass


@dataclass
class Deps:
    """외부 의존성. 테스트에서 가짜로 바꾼다."""

    fetch_video: Callable[[str, Path, Limits], FetchResult]
    extract_speech: Callable[[Path, Transcriber, Path, Limits], ExtractionResult]
    extract_screen_text: Callable[[Path, VisionReader, Path, Limits], ExtractionResult]
    transcriber: Callable[[], Transcriber]
    vision_reader: Callable[[], VisionReader]
    send_text: Callable[..., dict] = instagram.send_text
    limits: Limits = field(default_factory=Limits)


def default_deps(s: Settings) -> Deps:
    from .media import fetch, ocr, transcribe

    def make_transcriber() -> Transcriber:
        if s.transcriber == "faster-whisper":
            return transcribe.FasterWhisperTranscriber()
        return transcribe.OpenAIWhisperTranscriber()

    return Deps(fetch.fetch_video, transcribe.extract_speech, ocr.extract_screen_text,
                make_transcriber, ocr.OpenAIVisionReader)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reel(conn: psycopg.Connection, reel_id: int) -> dict:
    row = conn.execute("SELECT * FROM reels WHERE id=%s", (reel_id,)).fetchone()
    if row is None:
        raise PermanentError("reel_not_found")
    return row


def _save_extraction(conn: psycopg.Connection, reel_id: int, r: ExtractionResult) -> None:
    conn.execute(
        """INSERT INTO extractions (reel_id, medium, status, text, segments, error, extractor_version)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (reel_id, medium, extractor_version) DO UPDATE SET
             status=EXCLUDED.status, text=EXCLUDED.text, segments=EXCLUDED.segments,
             error=EXCLUDED.error, created_at=now()""",
        (reel_id, r.medium, r.status, r.text or None,
         json.dumps([sg.as_json() for sg in r.segments], ensure_ascii=False), r.error, r.extractor_version),
    )


def _save_caption(conn: psycopg.Connection, reel_id: int, caption: str | None) -> None:
    text = (caption or "").strip()
    _save_extraction(conn, reel_id, ExtractionResult("caption", "succeeded" if text else "empty", CAPTION_VERSION, text))


class Worker:
    def __init__(self, s: Settings, deps: Deps, http_client: httpx.Client | None = None):
        self.s = s
        self.deps = deps
        self.http = http_client or httpx.Client(timeout=15)
        self.handlers = {"fetch": self.handle_fetch, "transcribe": self.handle_transcribe,
                         "ocr": self.handle_ocr, "reply": self.handle_reply}

    def reel_dir(self, reel_id: int) -> Path:
        return self.s.data_dir / "reels" / str(reel_id)

    # --- 작업별 처리. 반환값은 jobs.result. 실패는 예외로 알린다 ---

    def handle_fetch(self, conn: psycopg.Connection, job: dict) -> dict:
        reel = _reel(conn, job["reel_id"])
        res = self.deps.fetch_video(reel["url"], self.reel_dir(reel["id"]), self.deps.limits)
        # 캡션: 웹훅 title을 우선, 없으면 yt-dlp 메타데이터. 영상 확보 실패와 무관하게 남긴다
        caption = reel["caption"] or res.caption
        _save_caption(conn, reel["id"], caption)
        if res.status != "fetched":
            permanent = (res.error or "").startswith(PERMANENT_FETCH_ERRORS)
            conn.execute("UPDATE reels SET fetch_status='failed', fetch_error=%s, caption=%s WHERE id=%s",
                         (res.error, caption, reel["id"]))
            conn.commit()  # 재시도하더라도 마지막 실패 이유는 보관함에 보이게 남긴다
            raise (PermanentError if permanent else RuntimeError)(res.error or "fetch_failed")
        conn.execute(
            """UPDATE reels SET fetch_status='fetched', fetch_error=NULL, fetch_method=%s,
                      video_path=%s, caption=%s WHERE id=%s""",
            (res.method, str(res.video_path), caption, reel["id"]),
        )
        for kind in ("transcribe", "ocr"):
            jobs.enqueue(conn, kind, reel_id=reel["id"], idempotency_key=f"{kind}:{reel['id']}")
        return {"method": res.method}

    def _extract(self, conn: psycopg.Connection, job: dict, run: Callable[[Path, Path], ExtractionResult]) -> dict:
        reel = _reel(conn, job["reel_id"])
        if reel["fetch_status"] != "fetched" or not reel["video_path"]:
            raise PermanentError("video_not_fetched")
        work = self.reel_dir(reel["id"]) / f"work-{job['id']}-{job['attempts']}"  # 실행별 분리
        try:
            r = run(Path(reel["video_path"]), work)
        finally:
            shutil.rmtree(work, ignore_errors=True)  # 임시 프레임·오디오 정리
        _save_extraction(conn, reel["id"], r)
        if r.status == "failed":
            conn.commit()
            raise RuntimeError(r.error or f"{r.medium}_failed")
        return {"status": r.status, "extractor_version": r.extractor_version, "segments": len(r.segments)}

    def handle_transcribe(self, conn: psycopg.Connection, job: dict) -> dict:
        t = self.deps.transcriber()
        return self._extract(conn, job, lambda v, w: self.deps.extract_speech(v, t, w, self.deps.limits))

    def handle_ocr(self, conn: psycopg.Connection, job: dict) -> dict:
        r = self.deps.vision_reader()
        return self._extract(conn, job, lambda v, w: self.deps.extract_screen_text(v, r, w, self.deps.limits))

    def handle_reply(self, conn: psycopg.Connection, job: dict) -> dict:
        p = job["payload"]
        if (job["result"] or {}).get("send_attempted_at"):
            # 이전 실행이 전송을 시도한 뒤 결과를 남기지 못했다. 이미 갔을 수 있으므로 다시 보내지 않는다
            raise PermanentError("send_outcome_unknown")
        ev = conn.execute("SELECT message_ts FROM webhook_events WHERE id=%s", (p["event_id"],)).fetchone()
        # 창은 Meta가 준 메시지 시각 기준. 시각을 모르면 보내지 않는다(늦은 재전달 대비)
        if ev is None or ev["message_ts"] is None or _now() - ev["message_ts"] > REPLY_WINDOW:
            raise PermanentError("outside_24h_window")
        self._mark_send_attempted(conn, job, _now().isoformat())
        try:
            res = self.deps.send_text(self.s.ig_access_token, self.s.ig_account_id, p["recipient_id"], p["text"],
                                      self.s.ig_graph_version, self.http)
        except httpx.HTTPStatusError as e:
            # 오류 응답을 받았으면 전달되지 않은 것. 4xx는 재시도해도 같고(권한·창 만료 등) 429·5xx만 재시도
            self._mark_send_attempted(conn, job, None)
            code = e.response.status_code
            err = f"send_http_{code}"
            raise (RuntimeError(err) if code == 429 or code >= 500 else PermanentError(err)) from None
        except httpx.ConnectError:
            self._mark_send_attempted(conn, job, None)  # 연결 자체가 안 됐으면 전달되지 않은 것
            raise RuntimeError("send_connect_error") from None
        except httpx.TransportError:
            raise PermanentError("send_outcome_unknown") from None  # 응답 유실: 갔는지 알 수 없음
        return {"message_id": res.get("message_id")}

    @staticmethod
    def _mark_send_attempted(conn: psycopg.Connection, job: dict, at: str | None) -> None:
        conn.execute("UPDATE jobs SET result=%s WHERE id=%s",
                     (json.dumps({"send_attempted_at": at}) if at else None, job["id"]))
        conn.commit()

    # --- 루프 ---

    def run_once(self, conn: psycopg.Connection) -> dict | None:
        job = jobs.claim(conn, self.s.job_lease_s, self.s.job_max_attempts)
        conn.commit()
        if job is None:
            return None
        started = _now()
        outcome = "succeeded"
        try:
            result = self.handlers[job["kind"]](conn, job)
            if not jobs.succeed(conn, job, result):
                conn.rollback()  # 임대가 만료돼 다른 워커가 가져간 작업. 이 실행의 기록은 버린다
                outcome = "lost"
        except Exception as e:
            conn.rollback()
            retryable = not isinstance(e, PermanentError)
            if retryable and not isinstance(e, RuntimeError):
                log.exception("job %s (%s) crashed", job["id"], job["kind"])
            err = str(e) or type(e).__name__
            outcome = jobs.fail(conn, job, err, retryable=retryable, max_attempts=self.s.job_max_attempts)
            log.warning("job %s (%s) %s: %s", job["id"], job["kind"], outcome, err)
        if job["reel_id"] is not None:
            conn.execute(
                """INSERT INTO processing_runs (reel_id, job_id, stage, outcome, started_at, finished_at)
                   VALUES (%s, %s, %s, %s, %s, now())""",
                (job["reel_id"], job["id"], job["kind"], outcome, started),
            )
        conn.commit()
        job["outcome"] = outcome
        return job

    def run_forever(self, idle_s: float = 2.0) -> None:
        stop = False

        def _stop(*_):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        while not stop:
            try:
                with db.connect(self.s.database_url) as conn:
                    while not stop:
                        if self.run_once(conn) is None:
                            time.sleep(idle_s)
            except psycopg.OperationalError:
                log.exception("db connection lost; retrying")
                time.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = get_settings()
    Worker(s, default_deps(s)).run_forever()


if __name__ == "__main__":
    main()
