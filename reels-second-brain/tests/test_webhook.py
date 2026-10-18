"""웹훅 수신 모의 테스트 (PRD 11장 1단계-A 테스트 목록)."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from conftest import load_fixture, sign
from rsb.app import create_app


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def post(client, settings, body: dict, *, secret=None):
    raw = json.dumps(body).encode()
    return client.post("/webhook/instagram", content=raw,
                       headers={"X-Hub-Signature-256": sign(secret or settings.ig_app_secret, raw),
                                "Content-Type": "application/json"})


def count(conn, table, where="TRUE"):
    return conn.execute(f"SELECT count(*) n FROM {table} WHERE {where}").fetchone()["n"]


def test_verify_get(client):
    ok = client.get("/webhook/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                  "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    bad = client.get("/webhook/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                   "hub.challenge": "12345"})
    assert bad.status_code == 403


def test_bad_signature_rejected_and_not_stored(client, settings, conn):
    r = post(client, settings, load_fixture("reel.json"), secret="wrong")
    assert r.status_code == 401
    raw = json.dumps(load_fixture("reel.json")).encode()
    assert client.post("/webhook/instagram", content=raw).status_code == 401  # 서명 헤더 없음
    assert count(conn, "webhook_events") == 0


def test_reel_intake_persists_before_200(client, settings, conn):
    r = post(client, settings, load_fixture("reel.json"))
    assert r.status_code == 200
    ev = conn.execute("SELECT * FROM webhook_events").fetchone()
    assert ev["kind"] == "reel" and ev["message_id"] == "mid.reel.1"
    assert int(ev["message_ts"].timestamp()) == 1760745600  # Meta timestamp(ms) 보존
    reel = conn.execute("SELECT * FROM reels").fetchone()
    assert reel["ig_video_id"] == "900001" and reel["caption"] == "엑셀 단축키 5가지"
    intake = conn.execute("SELECT * FROM intakes").fetchone()
    assert intake["note"] == "엑셀 팁" and intake["source"] == "dm" and intake["event_id"] == ev["id"]
    kinds = sorted(j["kind"] for j in conn.execute("SELECT kind FROM jobs"))
    assert kinds == ["fetch", "reply"]
    reply = conn.execute("SELECT payload FROM jobs WHERE kind='reply'").fetchone()["payload"]
    assert reply["text"] == "접수했어요" and reply["recipient_id"] == "1000000000000001"


def test_redelivery_same_message_id_is_noop(client, settings, conn):
    body = load_fixture("reel.json")
    assert post(client, settings, body).status_code == 200
    assert post(client, settings, body).status_code == 200
    assert count(conn, "webhook_events") == 1
    assert count(conn, "intakes") == 1
    assert count(conn, "jobs") == 2


def test_same_reel_resent_reuses_analysis(client, settings, conn):
    first = load_fixture("reel.json")
    again = copy.deepcopy(first)
    again["entry"][0]["messaging"][0]["message"]["mid"] = "mid.reel.2"
    post(client, settings, first)
    post(client, settings, again)
    assert count(conn, "reels") == 1
    assert count(conn, "intakes") == 2  # 접수 기록만 추가
    assert count(conn, "jobs", "kind='fetch'") == 1
    assert count(conn, "jobs", "kind='reply'") == 2


def test_non_allowed_sender_stored_as_ignored(client, settings, conn):
    body = load_fixture("reel.json")
    body["entry"][0]["messaging"][0]["sender"]["id"] = "999"
    assert post(client, settings, body).status_code == 200
    assert conn.execute("SELECT kind FROM webhook_events").fetchone()["kind"] == "ignored"
    assert count(conn, "reels") == 0 and count(conn, "jobs") == 0


def test_wrong_recipient_stored_as_ignored(client, settings, conn):
    body = load_fixture("reel.json")
    body["entry"][0]["messaging"][0]["recipient"]["id"] = "other-account"
    post(client, settings, body)
    assert conn.execute("SELECT kind FROM webhook_events").fetchone()["kind"] == "ignored"
    assert count(conn, "jobs") == 0


def test_echo_and_read_events_excluded(client, settings, conn):
    assert post(client, settings, load_fixture("echo.json")).status_code == 200
    assert count(conn, "webhook_events") == 0 and count(conn, "jobs") == 0


def test_multiple_attachments_each_intaken(client, settings, conn):
    post(client, settings, load_fixture("multi.json"))
    assert count(conn, "reels") == 2
    assert count(conn, "intakes") == 2
    assert count(conn, "jobs", "kind='fetch'") == 2
    replies = [j["payload"]["text"] for j in conn.execute("SELECT payload FROM jobs WHERE kind='reply'")]
    assert replies == ["접수했어요 / 지원하지 않는 형식이에요"]


def test_text_only_is_question_recorded_without_jobs(client, settings, conn):
    post(client, settings, load_fixture("text.json"))
    assert conn.execute("SELECT kind FROM webhook_events").fetchone()["kind"] == "text"
    assert count(conn, "jobs") == 0  # 질문 응답은 2단계


def test_unsupported_only(client, settings, conn):
    body = load_fixture("multi.json")
    body["entry"][0]["messaging"][0]["message"]["attachments"] = [{"type": "image", "payload": {"url": "https://x"}}]
    post(client, settings, body)
    assert conn.execute("SELECT kind FROM webhook_events").fetchone()["kind"] == "unsupported"
    assert [j["payload"]["text"] for j in conn.execute("SELECT payload FROM jobs")] == ["지원하지 않는 형식이에요"]


def test_db_failure_returns_5xx(client, settings, monkeypatch):
    from rsb import intake

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(intake, "record_message", boom)
    assert post(client, settings, load_fixture("reel.json")).status_code == 503


def test_partial_failure_rolls_back_whole_message(client, settings, conn, monkeypatch):
    """한 메시지의 기록 중 실패하면 webhook_events도 남지 않아 재전달 때 다시 처리된다."""
    from rsb import jobs

    def boom(*a, **k):
        raise RuntimeError("enqueue failed")
    monkeypatch.setattr(jobs, "enqueue", boom)
    assert post(client, settings, load_fixture("reel.json")).status_code == 503
    assert count(conn, "webhook_events") == 0 and count(conn, "reels") == 0
    monkeypatch.undo()
    assert post(client, settings, load_fixture("reel.json")).status_code == 200
    assert count(conn, "webhook_events") == 1 and count(conn, "jobs") == 2
