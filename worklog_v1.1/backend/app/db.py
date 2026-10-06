"""SQLite 엔진·세션. WAL / foreign_keys ON / busy_timeout / synchronous FULL, 쓰기 트랜잭션은 BEGIN IMMEDIATE.

BEGIN IMMEDIATE를 쓰는 이유: 일지 unique/revision 검사와 갱신 사이에 다른 쓰기가 끼어들지 못하게 하고,
읽기 락 → 쓰기 락 승격 중 발생하는 SQLITE_BUSY 교착을 피하기 위함이다.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings


def _json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def create_db_engine(settings: Settings, write: bool = True) -> Engine:
    """write=True: 모든 트랜잭션이 BEGIN IMMEDIATE. write=False: 읽기 전용 용도(WAL 스냅샷 읽기, 쓰기 락 없음)."""
    settings.ensure_dirs()
    engine = create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False, "timeout": settings.sqlite_busy_timeout_ms / 1000},
        json_serializer=_json_dumps,
        pool_pre_ping=False,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        dbapi_conn.isolation_level = None  # pysqlite 자동 BEGIN 비활성화, 아래 begin 훅에서 직접 제어
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
        cur.execute(f"PRAGMA synchronous={settings.sqlite_synchronous}")
        cur.close()

    if write:
        # 같은 프로세스 안의 쓰기 트랜잭션은 먼저 이 mutex 로 줄 세운다. SQLite busy handler 는 대기 순서가 없는 polling 이라
        # 20명이 동시에 저장하면 일부 요청이 수 초씩 굶는다(측정: p95 4.4초). mutex 를 먼저 잡으면 대기가 순서대로 처리되고,
        # SQLite 락은 다른 프로세스(백업/복원 도구)와의 경쟁에만 쓰인다.
        lock = threading.Lock()
        engine.write_lock = lock  # type: ignore[attr-defined]

        @event.listens_for(engine, "begin")
        def _on_begin(conn):  # noqa: ANN001
            lock.acquire()
            try:
                conn.connection.info["write_lock_held"] = True
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            except BaseException:
                _release(conn.connection)
                raise

        def _release(dbapi_wrapper) -> None:  # noqa: ANN001
            if dbapi_wrapper.info.pop("write_lock_held", False):
                lock.release()

        @event.listens_for(engine, "commit")
        def _on_commit(conn):  # noqa: ANN001
            _release(conn.connection)

        @event.listens_for(engine, "rollback")
        def _on_rollback(conn):  # noqa: ANN001
            _release(conn.connection)

        @event.listens_for(engine, "checkin")
        def _on_checkin(dbapi_conn, record):  # noqa: ANN001
            # 예외 경로 등으로 commit/rollback 이벤트 없이 반환되는 연결이 락을 쥐고 있지 않도록 마지막 안전망
            if record.info.pop("write_lock_held", False):
                lock.release()
    else:
        @event.listens_for(engine, "begin")
        def _on_begin_read(conn):  # noqa: ANN001
            conn.exec_driver_sql("BEGIN")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """짧은 쓰기 트랜잭션. 예외 시 rollback."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
