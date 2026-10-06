"""API 공통: 읽기/변경 실행 헬퍼, 멱등성, 에러 응답.

변경 요청은 하나의 쓰기 트랜잭션에서 actor 검증 → 멱등 조회 → 업무 처리 → 멱등 응답 저장 → commit 순으로 처리한다.
성공 응답은 DB commit 기준이며 JSON export 상태(meta.exportPending)와 구별한다.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import ExportJob
from ..runtime import Runtime
from ..services.common import (idempotent_lookup, idempotent_store, load_actor, payload_hash)

log = logging.getLogger("worklog.api")


def rt_of(request: Request) -> Runtime:
    return request.app.state.rt


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _export_pending(s: Session) -> bool:
    return bool(s.execute(select(func.count()).select_from(ExportJob).where(ExportJob.exported_revision < ExportJob.requested_revision)).scalar())


def read(request: Request, fn: Callable[[Session], Any]) -> dict:
    rt = rt_of(request)
    with rt.read_factory() as s:
        data = fn(s)
        pending = _export_pending(s)
    return {"data": data, "meta": {"requestId": request_id(request), "exportPending": pending}}


def mutate(request: Request, payload: Any, fn: Callable[[Session, str | None], Any], *, actor_required: bool = True,
           idempotent: bool = True, status_code: int = 200) -> tuple[int, dict]:
    rt = rt_of(request)
    if rt.maintenance:
        raise ApiError(503, "MAINTENANCE", rt.maintenance_reason or "점검 중입니다.", extra={"retryable": True})
    key = request.headers.get("Idempotency-Key")
    if idempotent and not key:
        raise ApiError(422, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더가 필요합니다.")
    if key and len(key) > 100:
        raise ApiError(422, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key가 너무 깁니다.")
    actor_id = request.headers.get("X-Actor-Id")
    scope = f"{request.method} {request.url.path}"
    req_hash = payload_hash({"path": request.url.path, "q": str(request.url.query), "body": payload})
    s = rt.write_factory()
    try:
        if actor_required or actor_id:
            load_actor(s, actor_id)
        if key:
            cached = idempotent_lookup(s, key, scope, req_hash)
            if cached is not None:
                s.rollback()
                code, body = cached
                body = {**body, "meta": {**body.get("meta", {}), "requestId": request_id(request), "replayed": True}}
                return code, body
        data = fn(s, actor_id)
        body = {"data": data, "meta": {"requestId": request_id(request), "exportPending": True}}
        if key:
            idempotent_store(s, key, scope, req_hash, status_code, body, rt.settings.idempotency_retention_days)
        s.commit()
        return status_code, body
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()


def error_body(err: ApiError, request: Request) -> dict:
    return err.body(request_id(request))
