"""요청 스키마 (camelCase). 알 수 없는 필드는 거부한다(조용한 무시 방지)."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ProjectStatus = Literal["preparing", "in_progress", "on_hold", "completed", "cancelled"]
MilestoneStatus = Literal["planned", "in_progress", "on_hold", "completed", "cancelled"]
Doc = dict[str, Any]


class Req(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ── 기준정보 ────────────────────────────────────────────────────────────────

class OrgCreate(Req):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["division", "team"]
    parent_id: str | None = None
    external_key: str | None = None


class OrgPatch(Req):
    expected_revision: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = None
    external_key: str | None = None
    active: bool | None = None


class UserCreate(Req):
    name: str = Field(min_length=1, max_length=100)
    team_id: str
    employee_number: str | None = None
    external_key: str | None = None


class UserPatch(Req):
    expected_revision: int
    name: str | None = Field(default=None, min_length=1, max_length=100)
    team_id: str | None = None
    employee_number: str | None = None
    external_key: str | None = None
    active: bool | None = None


class ImportCommit(Req):
    preview_token: str


class ProjectCreate(Req):
    name: str = Field(min_length=1, max_length=200)
    team_id: str
    owner_user_id: str
    member_ids: list[str] = Field(default_factory=list)
    is_short_term: bool = False
    status: ProjectStatus = "preparing"
    start_date: date | None = None
    end_date: date | None = None
    background_doc: Doc | None = None
    purpose_doc: Doc | None = None


class ProjectPatch(Req):
    expected_revision: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    team_id: str | None = None
    owner_user_id: str | None = None
    member_ids: list[str] | None = None
    is_short_term: bool | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    background_doc: Doc | None = None
    purpose_doc: Doc | None = None
    retrospective_doc: Doc | None = None
    clear_dates: bool = False


class ProjectCopy(Req):
    name: str = Field(min_length=1, max_length=200)
    copy_milestones: bool = False
    copy_kpis: bool = False


class MilestoneCreate(Req):
    name: str = Field(min_length=1, max_length=200)
    description_doc: Doc | None = None
    planned_start: date | None = None
    planned_end: date | None = None


class MilestonePatch(Req):
    expected_revision: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description_doc: Doc | None = None
    status: MilestoneStatus | None = None
    sort_order: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    clear_planned: bool = False


class BaselineConfirm(Req):
    expected_revision: int


class KpiCreate(Req):
    name: str = Field(min_length=1, max_length=200)
    unit: str | None = None
    baseline_value: str | None = None
    target_value: str | None = None
    direction: Literal["increase", "decrease", "target"] | None = None


class KpiPatch(Req):
    expected_revision: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = None
    baseline_value: str | None = None
    target_value: str | None = None
    direction: Literal["increase", "decrease", "target"] | None = None
    active: bool | None = None


# ── 일지 ────────────────────────────────────────────────────────────────────

class AttachmentUseIn(Req):
    id: str | None = None  # task_attachments.id (본문 image node 의 attachmentUseId)
    attachment_id: str
    title: str | None = None
    description: str = ""


class TaskIn(Req):
    id: str | None = None
    title: str | None = Field(default=None, max_length=200)  # TASK 이름(선택)
    milestone_id: str
    content: Doc
    performed_start: date | None = None
    performed_end: date | None = None
    attachments: list[AttachmentUseIn] = Field(default_factory=list)


class NewTracker(Req):
    client_entry_id: str = Field(min_length=1, max_length=64)
    content: Doc
    assignee_id: str | None = None
    due_date: date | None = None
    impact: Doc | None = None
    response: Doc | None = None


class AchievementIn(Req):
    id: str | None = None
    type: Literal["quantitative", "qualitative"]
    preset_key: str
    title: str | None = None
    content: Doc | None = None
    numeric_payload: dict[str, Any] | None = None
    kpi_id: str | None = None
    measured_on: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    source_task_id: str | None = None


class LogSave(Req):
    expected_revision: int = Field(ge=0)
    tasks: list[TaskIn] = Field(default_factory=list)
    new_todos: list[NewTracker] = Field(default_factory=list)
    new_issues: list[NewTracker] = Field(default_factory=list)
    hidden_tracker_ref_ids: list[str] = Field(default_factory=list)
    achievements: list[AchievementIn] = Field(default_factory=list)
    lesson_learned: Doc | None = None
    note: Doc | None = None
    collaborator_ids: list[str] = Field(default_factory=list)


# ── 트래커 ──────────────────────────────────────────────────────────────────

class TodoCreate(Req):
    content: Doc
    assignee_id: str | None = None
    due_date: date | None = None


class TodoPatch(Req):
    expected_revision: int
    content: Doc | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    status: Literal["open", "in_progress"] | None = None  # completed/cancelled 는 전용 동작으로만
    clear_assignee: bool = False
    clear_due_date: bool = False


class IssueCreate(Req):
    content: Doc
    assignee_id: str | None = None
    due_date: date | None = None
    impact: Doc | None = None
    response: Doc | None = None


class IssuePatch(Req):
    expected_revision: int
    content: Doc | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    impact: Doc | None = None
    response: Doc | None = None
    status: Literal["open", "in_progress"] | None = None
    clear_assignee: bool = False
    clear_due_date: bool = False


class AppendToLog(Req):
    date: date
    author_id: str
    milestone_id: str
    expected_log_revision: int = Field(ge=0)


class CompleteBody(Req):
    expected_revision: int
    result_text: str | None = None
    append_to_daily_log: AppendToLog | None = None


class SimpleTransition(Req):
    expected_revision: int


class IssueTodoCreate(Req):
    expected_issue_revision: int
    content: Doc
    assignee_id: str | None = None
    due_date: date | None = None


# ── 운영 ────────────────────────────────────────────────────────────────────

class RebuildBody(Req):
    project_id: str | None = None
    all: bool = False


class BundleBody(Req):
    project_id: str
    date_from: date | None = None
    date_to: date | None = None
    include_attachments: bool = False


class RestoreBody(Req):
    confirm: Literal["RESTORE"]


# ── 보고자료(PPT) ───────────────────────────────────────────────────────────

class ReportJobCreate(Req):
    kind: Literal["weekly", "period", "monthly"]
    template: Literal["weekly", "exec"] = "weekly"
    week: str | None = Field(default=None, max_length=8)
    date_from: date | None = None
    date_to: date | None = None
    month: str | None = Field(default=None, max_length=7)
    project_ids: list[str] = Field(min_length=1, max_length=100)
    org_label: str | None = Field(default=None, max_length=200)
    include_tables: bool = False
    include_gantts: bool = False
    include_milestone_gantt: bool = False
    refresh_ai: bool = False
    # 팀장 요약 페이지: 주간·기간 보고 + 주간업무 양식에서만 적용 (API 기본은 끔, 화면은 기본 켜서 보냄)
    include_team_summary: bool = False
    summary_author: str | None = Field(default=None, max_length=40)


class ReportResponse(Req):
    response_name: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=2_000_000)
