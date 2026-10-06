"""서비스 공통: audit, export dirty, revision 검사, idempotency, 직렬화 보조."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ApiError, conflict, not_found
from ..models import AuditEvent, BackupRun, ExportJob, IdempotencyRequest, User, utcnow

T = TypeVar("T")


# ── 시간 ────────────────────────────────────────────────────────────────────

def local_today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def iso_date(d: date | None) -> str | None:
    return d.isoformat() if d else None


# ── 조회/검증 ───────────────────────────────────────────────────────────────

def get_or_404(s: Session, model: type[T], id_: str, label: str, *, include_deleted: bool = False) -> T:
    obj = s.get(model, id_)
    if obj is None or (not include_deleted and getattr(obj, "deleted_at", None) is not None):
        raise not_found(label, id_)
    return obj


def load_actor(s: Session, actor_id: str | None) -> User:
    if not actor_id:
        raise ApiError(422, "ACTOR_REQUIRED", "작성자를 먼저 선택해 주세요. (X-Actor-Id)")
    user = s.get(User, actor_id)
    if user is None or user.deleted_at is not None:
        raise ApiError(422, "ACTOR_INVALID", "선택한 사용자를 찾을 수 없습니다.")
    if not user.active:
        raise ApiError(422, "ACTOR_INACTIVE", "비활성화된 사용자입니다.")
    return user


def check_revision(obj: Any, expected: int, label: str) -> None:
    if obj.revision != expected:
        raise conflict("REVISION_CONFLICT", f"{label}이(가) 다른 곳에서 수정되었습니다. 최신본을 확인해 주세요.",
                       current_revision=obj.revision, resource_id=obj.id)


def bump(obj: Any, actor_id: str | None) -> None:
    obj.revision += 1
    obj.updated_at = utcnow()
    obj.updated_by = actor_id


def stamp_new(obj: Any, actor_id: str | None) -> None:
    obj.created_by = actor_id
    obj.updated_by = actor_id


# ── audit / export ──────────────────────────────────────────────────────────

def audit(s: Session, action: str, entity_type: str, entity_id: str, actor_id: str | None,
          detail: dict | None = None, operation_id: str | None = None) -> None:
    s.add(AuditEvent(action=action, entity_type=entity_type, entity_id=entity_id, detail=detail,
                     actor_id=actor_id, operation_id=operation_id))


def mark_export(s: Session, kind: str, project_id: str | None = None, work_date: date | None = None) -> int:
    """export target를 dirty로 만든다. requested_revision 은 대상별 단조 증가 sourceRevision."""
    if kind == "master":
        key = "master"
    elif kind == "project":
        key = f"project:{project_id}"
    elif kind == "trackers":
        key = f"trackers:{project_id}"
    elif kind == "daily":
        key = f"daily:{project_id}:{work_date.isoformat()}"  # type: ignore[union-attr]
    else:  # pragma: no cover
        raise ValueError(kind)
    job = s.get(ExportJob, key)
    if job is None:
        job = ExportJob(target_key=key, kind=kind, project_id=project_id, work_date=work_date,
                        requested_revision=1, exported_revision=0, status="pending", attempts=0)
        s.add(job)
    else:
        job.requested_revision += 1
        job.status = "pending"
        job.next_attempt_at = None
        job.updated_at = utcnow()
    return job.requested_revision


def schedule_daily_backup(s: Session, settings: Settings) -> None:
    """로컬 날짜별 첫 성공 업무 저장 이후 백업을 예약한다. 같은 날짜 중복 예약은 unique index가 막는다."""
    today = local_today(settings)
    existing = s.execute(select(BackupRun).where(BackupRun.kind == "daily", BackupRun.local_date == today)).scalar_one_or_none()
    if existing is None:
        s.add(BackupRun(kind="daily", local_date=today, status="scheduled"))
    elif existing.status == "failed":
        existing.status = "scheduled"
        existing.error = None


# ── idempotency ─────────────────────────────────────────────────────────────

def payload_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def idempotent_lookup(s: Session, key: str, scope: str, req_hash: str) -> tuple[int, dict] | None:
    row = s.get(IdempotencyRequest, (key, scope))
    if row is None:
        return None
    if row.expires_at < utcnow():
        s.delete(row)
        s.flush()
        return None
    if row.request_hash != req_hash:
        raise conflict("IDEMPOTENCY_KEY_REUSED", "같은 Idempotency-Key로 다른 내용이 전송되었습니다.")
    return row.status_code, row.response_json or {}


def idempotent_store(s: Session, key: str, scope: str, req_hash: str, status: int, body: dict,
                     retention_days: int) -> None:
    s.add(IdempotencyRequest(key=key, scope=scope, request_hash=req_hash, status_code=status, response_json=body,
                             expires_at=utcnow() + timedelta(days=retention_days)))


def purge_expired_idempotency(s: Session) -> int:
    rows = s.execute(select(IdempotencyRequest).where(IdempotencyRequest.expires_at < utcnow())).scalars().all()
    for r in rows:
        s.delete(r)
    return len(rows)
