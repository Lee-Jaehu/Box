"""ORM 테이블. DB snake_case. 문서/KPI snapshot 등 구조 데이터만 JSON 컬럼을 사용한다."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """SQLite에는 naive UTC로 저장하고 읽을 때 tz-aware UTC로 돌려준다."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON, datetime: UTCDateTime, date: Date}


class Aggregate:
    """변경 가능한 aggregate 공통 필드."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


# ── 기준정보 ────────────────────────────────────────────────────────────────

class Organization(Aggregate, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # division | team
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (
        CheckConstraint("kind IN ('division','team')", name="ck_org_kind"),
        Index("uq_org_external_key", "external_key", unique=True, sqlite_where=(external_key.isnot(None))),
    )


class User(Aggregate, Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    employee_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (
        Index("uq_user_employee_number", "employee_number", unique=True, sqlite_where=(employee_number.isnot(None))),
        Index("uq_user_external_key", "external_key", unique=True, sqlite_where=(external_key.isnot(None))),
        Index("ix_user_team", "team_id"),
    )


class Project(Aggregate, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_short_term: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="preparing", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    background_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    purpose_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retrospective_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('preparing','in_progress','on_hold','completed','cancelled')", name="ck_project_status"),
        Index("ix_project_team", "team_id"),
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Milestone(Aggregate, Base):
    __tablename__ = "milestones"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_general: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('planned','in_progress','on_hold','completed','cancelled')", name="ck_ms_status"),
        Index("uq_milestone_general", "project_id", unique=True, sqlite_where=(is_general.is_(True))),
        Index("ix_milestone_project", "project_id"),
    )


class ProjectKpi(Aggregate, Base):
    __tablename__ = "project_kpis"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    baseline_value: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Decimal 문자열
    target_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (
        CheckConstraint("direction IS NULL OR direction IN ('increase','decrease','target')", name="ck_kpi_dir"),
        Index("ix_kpi_project", "project_id"),
    )


# ── 일지 ────────────────────────────────────────────────────────────────────

class DailyLog(Aggregate, Base):
    __tablename__ = "daily_logs"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    author_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lesson_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tasks: Mapped[list[LogTask]] = relationship(back_populates="log", order_by="LogTask.sort_order",
                                                cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("project_id", "author_id", "work_date", name="uq_log_project_author_date"),
        Index("ix_log_project_date", "project_id", "work_date"),
    )


class LogTask(Base):
    __tablename__ = "log_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    log_id: Mapped[str] = mapped_column(ForeignKey("daily_logs.id", ondelete="CASCADE"), nullable=False)
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)
    milestone_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 선택. 없으면 본문 첫 줄이 요약으로 쓰인다
    content_doc: Mapped[dict] = mapped_column(JSON, nullable=False)
    performed_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    performed_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    log: Mapped[DailyLog] = relationship(back_populates="tasks")
    attachments: Mapped[list[TaskAttachment]] = relationship(order_by="TaskAttachment.sort_order",
                                                             cascade="all, delete-orphan")
    __table_args__ = (Index("ix_task_log", "log_id"),)


class LogCollaborator(Base):
    __tablename__ = "log_collaborators"
    log_id: Mapped[str] = mapped_column(ForeignKey("daily_logs.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    team_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Achievement(Base):
    __tablename__ = "achievements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    log_id: Mapped[str] = mapped_column(ForeignKey("daily_logs.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    preset_key: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    numeric_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    kpi_id: Mapped[str | None] = mapped_column(ForeignKey("project_kpis.id"), nullable=True)
    kpi_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    measured_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (
        CheckConstraint("type IN ('quantitative','qualitative')", name="ck_ach_type"),
        Index("ix_ach_log", "log_id"),
    )


class LogTrackerRef(Base):
    __tablename__ = "log_tracker_refs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    log_id: Mapped[str] = mapped_column(ForeignKey("daily_logs.id", ondelete="CASCADE"), nullable=False)
    client_entry_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tracker_type: Mapped[str] = mapped_column(String(8), nullable=False)  # todo | issue
    tracker_id: Mapped[str] = mapped_column(String(36), nullable=False)
    original_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hidden_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    __table_args__ = (
        UniqueConstraint("log_id", "client_entry_id", name="uq_ref_log_client_entry"),
        CheckConstraint("tracker_type IN ('todo','issue')", name="ck_ref_type"),
    )


# ── 트래커 ──────────────────────────────────────────────────────────────────

class Todo(Aggregate, Base):
    __tablename__ = "todos"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    content_doc: Mapped[dict] = mapped_column(JSON, nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    source_log_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_issue_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('open','in_progress','completed','cancelled')", name="ck_todo_status"),
        Index("ix_todo_project", "project_id"),
    )


class Issue(Aggregate, Base):
    __tablename__ = "issues"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    content_doc: Mapped[dict] = mapped_column(JSON, nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    impact_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_doc: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    source_log_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('open','in_progress','resolved','closed')", name="ck_issue_status"),
        Index("ix_issue_project", "project_id"),
    )


class TrackerEvent(Base):
    __tablename__ = "tracker_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tracker_type: Mapped[str] = mapped_column(String(8), nullable=False)
    tracker_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    next_status: Mapped[str] = mapped_column(String(16), nullable=False)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    created_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (Index("ix_event_tracker", "tracker_type", "tracker_id"),)


# ── 첨부 ────────────────────────────────────────────────────────────────────

class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_relative_path: Mapped[str] = mapped_column(String(300), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(12), default="temp", nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    __table_args__ = (CheckConstraint("state IN ('temp','committed')", name="ck_att_state"),)


class TaskAttachment(Base):
    """첨부 사용처. 본문 image node는 이 id(attachmentUseId)를 참조한다."""

    __tablename__ = "task_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("log_tasks.id", ondelete="CASCADE"), nullable=False)
    attachment_id: Mapped[str] = mapped_column(ForeignKey("attachments.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attachment: Mapped[Attachment] = relationship()
    __table_args__ = (Index("ix_taskatt_task", "task_id"), Index("ix_taskatt_att", "attachment_id"))


# ── 내부 ────────────────────────────────────────────────────────────────────

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


class IdempotencyRequest(Base):
    __tablename__ = "idempotency_requests"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    scope: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class ExportJob(Base):
    __tablename__ = "export_jobs"
    target_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # master|project|daily|trackers
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    exported_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    __table_args__ = (Index("ix_export_status", "status"),)


class ImportPreview(Base):
    __tablename__ = "import_previews"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity: Mapped[str] = mapped_column(String(16), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rows: Mapped[list] = mapped_column(JSON, nullable=False)
    has_errors: Mapped[bool] = mapped_column(Boolean, nullable=False)
    base_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # daily|manual|pre_restore
    local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False)  # scheduled|running|succeeded|failed
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    __table_args__ = (
        Index("uq_backup_daily", "local_date", unique=True,
              sqlite_where=(kind == "daily")),
    )


class AppMetadata(Base):
    __tablename__ = "app_metadata"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
