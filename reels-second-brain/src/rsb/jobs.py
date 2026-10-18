"""PostgreSQL jobs 테이블 기반 영구 큐 (PRD 5장, D15)."""

from __future__ import annotations

import json

import psycopg

# 재시도 대기(초). 시도 횟수별
BACKOFF_S = (30, 120, 600)


def enqueue(conn: psycopg.Connection, kind: str, *, reel_id: int | None = None,
            payload: dict | None = None, idempotency_key: str | None = None) -> int | None:
    """같은 idempotency_key가 이미 있으면 등록하지 않고 None."""
    row = conn.execute(
        """INSERT INTO jobs (kind, reel_id, payload, idempotency_key) VALUES (%s, %s, %s, %s)
           ON CONFLICT (idempotency_key) DO NOTHING RETURNING id""",
        (kind, reel_id, json.dumps(payload or {}), idempotency_key),
    ).fetchone()
    return row["id"] if row else None


def claim(conn: psycopg.Connection, lease_s: int, max_attempts: int) -> dict | None:
    """대기 중이거나 임대가 만료된 작업 1개를 가져온다. 다른 워커와 겹치지 않는다."""
    with conn.transaction():
        # 임대 만료 + 시도 소진 작업은 실패로 닫는다(워커가 처리 중 죽은 경우)
        conn.execute(
            """UPDATE jobs SET status='failed', last_error=coalesce(last_error, 'lease_expired'), updated_at=now()
               WHERE status='running' AND lease_until < now() AND attempts >= %s""",
            (max_attempts,),
        )
        return conn.execute(
            """UPDATE jobs SET status='running', attempts=attempts+1,
                      lease_until=now() + make_interval(secs => %s), updated_at=now()
               WHERE id = (
                 SELECT id FROM jobs
                 WHERE (status='queued' AND run_after <= now())
                    OR (status='running' AND lease_until < now())
                 ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
               RETURNING *""",
            (lease_s,),
        ).fetchone()


def succeed(conn: psycopg.Connection, job_id: int, result: dict | None = None) -> None:
    conn.execute(
        "UPDATE jobs SET status='succeeded', result=%s, lease_until=NULL, last_error=NULL, updated_at=now() WHERE id=%s",
        (json.dumps(result) if result is not None else None, job_id),
    )


def fail(conn: psycopg.Connection, job: dict, error: str, *, retryable: bool, max_attempts: int) -> str:
    """재시도 가능하고 시도가 남았으면 queued로 되돌린다. 최종 상태를 반환."""
    if retryable and job["attempts"] < max_attempts:
        delay = BACKOFF_S[min(job["attempts"] - 1, len(BACKOFF_S) - 1)]
        conn.execute(
            """UPDATE jobs SET status='queued', last_error=%s, lease_until=NULL,
                      run_after=now() + make_interval(secs => %s), updated_at=now() WHERE id=%s""",
            (error[:2000], delay, job["id"]),
        )
        return "queued"
    conn.execute(
        "UPDATE jobs SET status='failed', last_error=%s, lease_until=NULL, updated_at=now() WHERE id=%s",
        (error[:2000], job["id"]),
    )
    return "failed"
