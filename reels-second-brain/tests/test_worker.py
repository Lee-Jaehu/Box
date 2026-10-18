"""jobs 워커 모의 테스트. 외부 의존성(다운로드·전사·판독·Send API)은 가짜로 바꾼다."""

import threading
from pathlib import Path

import httpx
import pytest

from rsb import db, intake, jobs
from rsb.instagram import IncomingMessage, ReelAttachment
from rsb.media.types import ExtractionResult, FetchResult, Segment
from rsb.worker import Deps, Worker


class FakeT:
    version = "fake-t"


class FakeV:
    version = "fake-v"


def make_deps(fetch=None, speech=None, screen=None, send=None):
    def default_fetch(url, dest, limits):
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / "video.mp4"
        p.write_bytes(b"fake")
        return FetchResult("fetched", p, "direct")

    return Deps(
        fetch_video=fetch or default_fetch,
        extract_speech=speech or (lambda v, t, w, l: ExtractionResult(
            "audio", "succeeded", f"transcribe@1+{t.version}", "안녕하세요", [Segment(0.0, 1.5, "안녕하세요")])),
        extract_screen_text=screen or (lambda v, r, w, l: ExtractionResult(
            "screen", "empty", f"ocr@1+{r.version}")),
        transcriber=FakeT, vision_reader=FakeV,
        send_text=send or (lambda *a, **k: {"message_id": "out.1"}),
    )


def receive(conn, mid="mid.1", video_id="v1", title="캡션"):
    m = IncomingMessage(mid, "1000000000000001", "17841400000000001", None,
                        [ReelAttachment("https://lookaside.fbsbx.com/x", video_id, title)])
    with conn.transaction():
        intake.record_message(conn, m, allowed=True)


def drain(worker, conn, limit=20):
    done = []
    for _ in range(limit):
        j = worker.run_once(conn)
        if j is None:
            break
        done.append((j["kind"], j["outcome"]))
    return done


def test_full_pipeline(conn, settings):
    receive(conn)
    w = Worker(settings, make_deps())
    done = drain(w, conn)
    assert sorted(done) == [("fetch", "succeeded"), ("ocr", "succeeded"), ("reply", "succeeded"),
                            ("transcribe", "succeeded")]
    reel = conn.execute("SELECT * FROM reels").fetchone()
    assert reel["fetch_status"] == "fetched" and reel["fetch_method"] == "direct"
    ext = {e["medium"]: e for e in conn.execute("SELECT * FROM extractions")}
    assert ext["audio"]["status"] == "succeeded"
    assert ext["audio"]["segments"] == [{"start": 0.0, "end": 1.5, "text": "안녕하세요"}]
    assert ext["screen"]["status"] == "empty"
    assert ext["caption"]["status"] == "succeeded" and ext["caption"]["text"] == "캡션"
    runs = conn.execute("SELECT stage, outcome FROM processing_runs ORDER BY id").fetchall()
    assert {r["stage"] for r in runs} == {"fetch", "transcribe", "ocr"}
    reply = conn.execute("SELECT result FROM jobs WHERE kind='reply'").fetchone()
    assert reply["result"] == {"message_id": "out.1"}


def test_fetch_failure_keeps_caption_and_retries(conn, settings):
    receive(conn)
    calls = []

    def flaky(url, dest, limits):
        calls.append(1)
        return FetchResult("failed", error="timeout", caption=None)
    w = Worker(settings, make_deps(fetch=flaky))
    w.run_once(conn)  # reply or fetch
    w.run_once(conn)
    job = conn.execute("SELECT * FROM jobs WHERE kind='fetch'").fetchone()
    assert job["status"] == "queued" and job["attempts"] == 1 and job["last_error"] == "timeout"
    reel = conn.execute("SELECT * FROM reels").fetchone()
    assert reel["fetch_status"] == "failed" and reel["fetch_error"] == "timeout"
    assert conn.execute("SELECT status FROM extractions WHERE medium='caption'").fetchone()["status"] == "succeeded"
    # 대기 시간 경과 후 최대 시도 수까지 재시도하고 failed
    for _ in range(5):
        conn.execute("UPDATE jobs SET run_after=now() WHERE kind='fetch'")
        conn.commit()
        w.run_once(conn)
    job = conn.execute("SELECT * FROM jobs WHERE kind='fetch'").fetchone()
    assert job["status"] == "failed" and job["attempts"] == settings.job_max_attempts
    assert len(calls) == settings.job_max_attempts


def test_permanent_fetch_error_not_retried(conn, settings):
    receive(conn)
    w = Worker(settings, make_deps(fetch=lambda u, d, l: FetchResult("failed", error="blocked_url:non_public_ip")))
    drain(w, conn)
    job = conn.execute("SELECT * FROM jobs WHERE kind='fetch'").fetchone()
    assert job["status"] == "failed" and job["attempts"] == 1
    assert conn.execute("SELECT count(*) n FROM jobs WHERE kind IN ('transcribe','ocr')").fetchone()["n"] == 0


def test_partial_extraction_status_per_medium(conn, settings):
    """음성 성공·화면 실패를 매체별로 따로 남긴다."""
    receive(conn)
    w = Worker(settings, make_deps(screen=lambda v, r, wd, l: ExtractionResult(
        "screen", "failed", "ocr@1+fake-v", error="ocr_failed:APIError")))
    drain(w, conn)
    ext = {e["medium"]: e["status"] for e in conn.execute("SELECT medium, status FROM extractions")}
    assert ext == {"audio": "succeeded", "screen": "failed", "caption": "succeeded"}
    assert conn.execute("SELECT status FROM jobs WHERE kind='ocr'").fetchone()["status"] == "queued"


def test_reply_outside_24h_window_not_sent(conn, settings):
    receive(conn)
    conn.execute("UPDATE webhook_events SET received_at = now() - interval '25 hours'")
    conn.commit()
    sent = []
    w = Worker(settings, make_deps(send=lambda *a, **k: sent.append(a) or {}))
    drain(w, conn)
    job = conn.execute("SELECT * FROM jobs WHERE kind='reply'").fetchone()
    assert job["status"] == "failed" and job["last_error"] == "outside_24h_window" and sent == []


@pytest.mark.parametrize("code,expected", [(400, "failed"), (503, "queued")])
def test_reply_http_errors(conn, settings, code, expected):
    receive(conn)

    def send(*a, **k):
        req = httpx.Request("POST", "https://graph.instagram.com")
        raise httpx.HTTPStatusError("x", request=req, response=httpx.Response(code, request=req))
    w = Worker(settings, make_deps(send=send))
    drain(w, conn)
    assert conn.execute("SELECT status FROM jobs WHERE kind='reply'").fetchone()["status"] == expected


def test_expired_lease_is_reclaimed(conn, settings):
    """워커가 처리 중 죽으면 임대 만료 후 다른 워커가 이어서 처리한다."""
    receive(conn)
    job = jobs.claim(conn, 900, 3)
    conn.commit()
    assert jobs.claim(conn, 900, 3)["id"] != job["id"]  # 임대 중인 작업은 다시 안 나옴
    conn.execute("UPDATE jobs SET lease_until = now() - interval '1 second' WHERE id=%s", (job["id"],))
    conn.commit()
    again = jobs.claim(conn, 900, 3)
    conn.commit()
    assert again["id"] == job["id"] and again["attempts"] == 2


def test_expired_lease_with_exhausted_attempts_fails(conn, settings):
    receive(conn)
    conn.execute("UPDATE jobs SET status='running', attempts=3, lease_until=now() - interval '1 second'")
    conn.commit()
    assert jobs.claim(conn, 900, 3) is None
    conn.commit()
    assert {r["status"] for r in conn.execute("SELECT status FROM jobs")} == {"failed"}


def test_concurrent_claims_do_not_overlap(conn, settings, database_url):
    for i in range(10):
        receive(conn, mid=f"mid.{i}", video_id=f"v{i}")
    claimed: list[int] = []
    lock = threading.Lock()

    def worker():
        with db.connect(database_url) as c:
            while (j := jobs.claim(c, 900, 3)) is not None:
                c.commit()
                with lock:
                    claimed.append(j["id"])
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 20 and len(set(claimed)) == 20


def test_extract_without_video_is_permanent(conn, settings):
    receive(conn)
    reel_id = conn.execute("SELECT id FROM reels").fetchone()["id"]
    jobs.enqueue(conn, "transcribe", reel_id=reel_id, idempotency_key="t")
    conn.execute("DELETE FROM jobs WHERE kind <> 'transcribe'")
    conn.commit()
    w = Worker(settings, make_deps())
    w.run_once(conn)
    job = conn.execute("SELECT * FROM jobs").fetchone()
    assert job["status"] == "failed" and job["last_error"] == "video_not_fetched"


def test_work_dir_cleaned(conn, settings, tmp_path):
    receive(conn)
    seen = {}

    def speech(v, t, w, l):
        w.mkdir(parents=True)
        (w / "audio.wav").write_bytes(b"x")
        seen["w"] = w
        return ExtractionResult("audio", "empty", "transcribe@1+fake-t")
    drain(Worker(settings, make_deps(speech=speech)), conn)
    assert not Path(seen["w"]).exists()
