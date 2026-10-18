"""웹훅 메시지 → 영구 접수 기록 (PRD 8.1 처리 순서 4~5단계).

한 메시지의 webhook_events·reels·intakes·jobs는 호출자의 한 트랜잭션 안에서 기록한다.
"""

from __future__ import annotations

import json

import psycopg

from . import jobs
from .instagram import IncomingMessage, classify

ACK_TEXT = "접수했어요"
UNSUPPORTED_TEXT = "지원하지 않는 형식이에요"


def record_message(conn: psycopg.Connection, m: IncomingMessage, *, allowed: bool) -> int | None:
    """새 메시지면 event id, 같은 message_id 재전달이면 None."""
    kind = classify(m) if allowed else "ignored"
    row = conn.execute(
        """INSERT INTO webhook_events (message_id, sender_id, recipient_id, kind, payload)
           VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING RETURNING id""",
        (m.message_id, m.sender_id, m.recipient_id, kind, json.dumps(m.raw)),
    ).fetchone()
    if row is None or not allowed:
        return row["id"] if row else None
    event_id = row["id"]

    for att in m.reels:
        reel_id, is_new = _upsert_reel(conn, att.url, att.video_id, att.title)
        conn.execute(
            "INSERT INTO intakes (reel_id, event_id, source, note) VALUES (%s, %s, 'dm', %s)",
            (reel_id, event_id, m.text),
        )
        if is_new:
            jobs.enqueue(conn, "fetch", reel_id=reel_id, idempotency_key=f"fetch:{reel_id}")

    reply = _reply_text(m)
    if reply:
        jobs.enqueue(conn, "reply", payload={"recipient_id": m.sender_id, "text": reply, "event_id": event_id},
                     idempotency_key=f"reply:{m.message_id}")
    # 첨부 없는 텍스트는 질문이다. 질문 응답은 2단계 범위라 기록만 한다.
    return event_id


def _upsert_reel(conn: psycopg.Connection, url: str, video_id: str | None, title: str | None) -> tuple[int, bool]:
    """같은 릴스(video id 기준)면 기존 행을 재사용한다. id가 없으면 새 행."""
    if video_id:
        row = conn.execute(
            """INSERT INTO reels (ig_video_id, url, caption) VALUES (%s, %s, %s)
               ON CONFLICT (ig_video_id) DO NOTHING RETURNING id""",
            (video_id, url, title),
        ).fetchone()
        if row:
            return row["id"], True
        return conn.execute("SELECT id FROM reels WHERE ig_video_id=%s", (video_id,)).fetchone()["id"], False
    row = conn.execute("INSERT INTO reels (url, caption) VALUES (%s, %s) RETURNING id", (url, title)).fetchone()
    return row["id"], True


def _reply_text(m: IncomingMessage) -> str | None:
    parts = []
    if m.reels:
        parts.append(ACK_TEXT)
    if m.unsupported:
        parts.append(UNSUPPORTED_TEXT)
    return " / ".join(parts) or None
