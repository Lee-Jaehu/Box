"""To-Do / Issue 트래커. 프로젝트 단위의 현재 관리 상태이며 일별 TASK 와 상시 연결하지 않는다.

완료/해결 + 선택 TASK 생성은 하나의 트랜잭션이다: tracker 상태, 이벤트, 일지(TASK/revision), export dirty, 멱등 응답.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import faults
from ..config import Settings
from ..documents import has_content, make_document, require_valid
from ..errors import conflict, validation
from ..models import Issue, Project, Todo, TrackerEvent, User, utcnow
from ..schemas import (CompleteBody, IssueCreate, IssuePatch, IssueTodoCreate, SimpleTransition, TodoCreate, TodoPatch)
from .common import audit, bump, check_revision, get_or_404, iso, iso_date, local_today, mark_export, schedule_daily_backup
from .logs import append_result_task
from .masters import paginate
from .projects import require_active_project

OPEN_STATES = {"todo": {"open", "in_progress"}, "issue": {"open", "in_progress"}}


def _events(s: Session, ttype: str, tid: str) -> list[dict]:
    rows = s.execute(select(TrackerEvent).where(TrackerEvent.tracker_type == ttype, TrackerEvent.tracker_id == tid)
                     .order_by(TrackerEvent.occurred_at, TrackerEvent.id)).scalars().all()
    return [{"id": e.id, "previousStatus": e.previous_status, "nextStatus": e.next_status, "resultText": e.result_text,
             "actorId": e.actor_id, "occurredAt": iso(e.occurred_at), "createdTaskId": e.created_task_id} for e in rows]


def _assignee(s: Session, uid: str | None) -> str | None:
    u = s.get(User, uid) if uid else None
    return u.name if u else None


def ser_todo(s: Session, t: Todo, today: date | None = None, *, events: bool = False) -> dict:
    d = {"id": t.id, "projectId": t.project_id, "content": t.content_doc, "assigneeId": t.assignee_id,
         "assigneeName": _assignee(s, t.assignee_id), "dueDate": iso_date(t.due_date), "status": t.status,
         "overdue": bool(today and t.due_date and t.due_date < today and t.status in OPEN_STATES["todo"]),
         "sourceLogId": t.source_log_id, "sourceIssueId": t.source_issue_id, "revision": t.revision,
         "deletedAt": iso(t.deleted_at), "createdAt": iso(t.created_at), "updatedAt": iso(t.updated_at)}
    if events:
        d["events"] = _events(s, "todo", t.id)
    return d


def ser_issue(s: Session, i: Issue, today: date | None = None, *, events: bool = False) -> dict:
    d = {"id": i.id, "projectId": i.project_id, "content": i.content_doc, "assigneeId": i.assignee_id,
         "assigneeName": _assignee(s, i.assignee_id), "dueDate": iso_date(i.due_date), "impact": i.impact_doc,
         "response": i.response_doc, "status": i.status,
         "overdue": bool(today and i.due_date and i.due_date < today and i.status in OPEN_STATES["issue"]),
         "sourceLogId": i.source_log_id, "revision": i.revision, "deletedAt": iso(i.deleted_at),
         "createdAt": iso(i.created_at), "updatedAt": iso(i.updated_at)}
    if events:
        d["events"] = _events(s, "issue", i.id)
        d["responseTodoIds"] = [t for t in s.execute(select(Todo.id).where(Todo.source_issue_id == i.id)).scalars()]
    return d


def _check_assignee(s: Session, uid: str | None) -> None:
    if uid:
        u = s.get(User, uid)
        if u is None or u.deleted_at is not None:
            raise validation("담당자를 찾을 수 없습니다.", [{"field": "assigneeId", "code": "NOT_FOUND", "message": "담당자"}])


def _doc(settings: Settings, doc: dict, field: str, *, required: bool = True) -> None:
    require_valid(doc, settings, field)
    if required and not has_content(doc["doc"]):
        raise validation("내용을 입력해 주세요.", [{"field": field, "code": "REQUIRED", "message": "내용을 입력해 주세요."}])


# ── 조회 ────────────────────────────────────────────────────────────────────

def list_todos(s: Session, settings: Settings, project_id: str, status: str | None, assignee_id: str | None,
               limit: int, cursor: str | None) -> dict:
    get_or_404(s, Project, project_id, "프로젝트", include_deleted=True)
    stmt = select(Todo).where(Todo.project_id == project_id, Todo.deleted_at.is_(None)).order_by(Todo.created_at.desc(), Todo.id)
    if status:
        stmt = stmt.where(Todo.status == status)
    if assignee_id:
        stmt = stmt.where(Todo.assignee_id == assignee_id)
    rows, nxt = paginate(s, stmt, limit, cursor)
    today = local_today(settings)
    return {"items": [ser_todo(s, t, today) for t in rows], "nextCursor": nxt}


def list_issues(s: Session, settings: Settings, project_id: str, status: str | None, assignee_id: str | None,
                limit: int, cursor: str | None) -> dict:
    get_or_404(s, Project, project_id, "프로젝트", include_deleted=True)
    stmt = select(Issue).where(Issue.project_id == project_id, Issue.deleted_at.is_(None)).order_by(Issue.created_at.desc(), Issue.id)
    if status:
        stmt = stmt.where(Issue.status == status)
    if assignee_id:
        stmt = stmt.where(Issue.assignee_id == assignee_id)
    rows, nxt = paginate(s, stmt, limit, cursor)
    today = local_today(settings)
    return {"items": [ser_issue(s, i, today) for i in rows], "nextCursor": nxt}


def get_todo(s: Session, settings: Settings, todo_id: str) -> dict:
    return ser_todo(s, get_or_404(s, Todo, todo_id, "To-Do", include_deleted=True), local_today(settings), events=True)


def get_issue(s: Session, settings: Settings, issue_id: str) -> dict:
    return ser_issue(s, get_or_404(s, Issue, issue_id, "Issue", include_deleted=True), local_today(settings), events=True)


# ── 생성/수정/삭제 ──────────────────────────────────────────────────────────

def create_todo(s: Session, settings: Settings, project_id: str, body: TodoCreate, actor_id: str, *,
                source_issue_id: str | None = None) -> dict:
    require_active_project(s, project_id)
    _doc(settings, body.content, "content")
    _check_assignee(s, body.assignee_id)
    t = Todo(project_id=project_id, content_doc=body.content, assignee_id=body.assignee_id, due_date=body.due_date,
             source_issue_id=source_issue_id)
    t.created_by = t.updated_by = actor_id
    s.add(t)
    s.flush()
    audit(s, "todo.create", "todo", t.id, actor_id, {"sourceIssueId": source_issue_id})
    mark_export(s, "trackers", project_id)
    schedule_daily_backup(s, settings)
    return ser_todo(s, t, local_today(settings))


def create_issue(s: Session, settings: Settings, project_id: str, body: IssueCreate, actor_id: str) -> dict:
    require_active_project(s, project_id)
    _doc(settings, body.content, "content")
    for f, d in (("impact", body.impact), ("response", body.response)):
        if d is not None:
            require_valid(d, settings, f)
    _check_assignee(s, body.assignee_id)
    i = Issue(project_id=project_id, content_doc=body.content, assignee_id=body.assignee_id, due_date=body.due_date,
              impact_doc=body.impact, response_doc=body.response)
    i.created_by = i.updated_by = actor_id
    s.add(i)
    s.flush()
    audit(s, "issue.create", "issue", i.id, actor_id)
    mark_export(s, "trackers", project_id)
    schedule_daily_backup(s, settings)
    return ser_issue(s, i, local_today(settings))


def patch_todo(s: Session, settings: Settings, todo_id: str, body: TodoPatch, actor_id: str) -> dict:
    t = get_or_404(s, Todo, todo_id, "To-Do")
    require_active_project(s, t.project_id)
    check_revision(t, body.expected_revision, "To-Do")
    if t.status in {"completed", "cancelled"} and body.status is not None:
        raise conflict("STATE_CONFLICT", "완료된 항목의 상태는 '다시 열기'로만 바꿀 수 있습니다.")
    if body.content is not None:
        _doc(settings, body.content, "content")
        t.content_doc = body.content
    if body.clear_assignee:
        t.assignee_id = None
    elif "assignee_id" in body.model_fields_set:
        _check_assignee(s, body.assignee_id)
        t.assignee_id = body.assignee_id
    if body.clear_due_date:
        t.due_date = None
    elif "due_date" in body.model_fields_set:
        t.due_date = body.due_date
    prev = t.status
    if body.status is not None:
        t.status = body.status
    bump(t, actor_id)
    s.flush()
    audit(s, "todo.update", "todo", t.id, actor_id, {"status": [prev, t.status]})
    mark_export(s, "trackers", t.project_id)
    return ser_todo(s, t, local_today(settings), events=True)


def patch_issue(s: Session, settings: Settings, issue_id: str, body: IssuePatch, actor_id: str) -> dict:
    i = get_or_404(s, Issue, issue_id, "Issue")
    require_active_project(s, i.project_id)
    check_revision(i, body.expected_revision, "Issue")
    if i.status in {"resolved", "closed"} and body.status is not None:
        raise conflict("STATE_CONFLICT", "해결/종결된 항목의 상태는 '다시 열기'로만 바꿀 수 있습니다.")
    if body.content is not None:
        _doc(settings, body.content, "content")
        i.content_doc = body.content
    for attr, field in (("impact", "impact_doc"), ("response", "response_doc")):
        if attr in body.model_fields_set:
            doc = getattr(body, attr)
            if doc is not None:
                require_valid(doc, settings, attr)
            setattr(i, field, doc)
    if body.clear_assignee:
        i.assignee_id = None
    elif "assignee_id" in body.model_fields_set:
        _check_assignee(s, body.assignee_id)
        i.assignee_id = body.assignee_id
    if body.clear_due_date:
        i.due_date = None
    elif "due_date" in body.model_fields_set:
        i.due_date = body.due_date
    if body.status is not None:
        i.status = body.status
    bump(i, actor_id)
    s.flush()
    audit(s, "issue.update", "issue", i.id, actor_id)
    mark_export(s, "trackers", i.project_id)
    return ser_issue(s, i, local_today(settings), events=True)


def delete_tracker(s: Session, kind: str, tracker_id: str, expected_revision: int, actor_id: str) -> dict:
    model = Todo if kind == "todo" else Issue
    t = get_or_404(s, model, tracker_id, "항목")
    require_active_project(s, t.project_id)
    check_revision(t, expected_revision, "항목")
    t.deleted_at = utcnow()  # 출처 일지와 완료로 생성된 TASK 는 그대로 유지된다.
    bump(t, actor_id)
    audit(s, f"{kind}.delete", kind, t.id, actor_id)
    mark_export(s, "trackers", t.project_id)
    return {"id": t.id, "deletedAt": iso(t.deleted_at), "revision": t.revision}


# ── 상태 전환 ───────────────────────────────────────────────────────────────

def _transition(s: Session, settings: Settings, kind: str, tracker, next_status: str, body_revision: int,
                result_text: str | None, append, actor_id: str, allowed_from: set[str]) -> dict:
    require_active_project(s, tracker.project_id)
    check_revision(tracker, body_revision, "항목")
    if tracker.status not in allowed_from:
        raise conflict("STATE_CONFLICT", f"현재 상태({tracker.status})에서는 처리할 수 없습니다. 이미 처리되었을 수 있습니다.",
                       current_revision=tracker.revision, resource_id=tracker.id)
    text = (result_text or "").strip()
    if append is not None and not text:
        raise validation("오늘 한 일에 남기려면 결과를 입력해 주세요.",
                         [{"field": "resultText", "code": "REQUIRED", "message": "결과를 입력해 주세요."}])
    prev = tracker.status
    event = TrackerEvent(tracker_type=kind, tracker_id=tracker.id, previous_status=prev, next_status=next_status,
                         result_text=text or None, actor_id=actor_id)
    s.add(event)
    s.flush()
    faults.maybe("after_tracker_event")
    task = log = None
    if append is not None:
        task, log = append_result_task(s, settings, tracker.project_id, append.author_id, append.date, append.milestone_id,
                                       make_document(text), append.expected_log_revision, actor_id, event.id)
        event.created_task_id = task.id
        faults.maybe("after_log_append")
    tracker.status = next_status
    bump(tracker, actor_id)
    s.flush()
    audit(s, f"{kind}.{next_status}", kind, tracker.id, actor_id,
          {"previous": prev, "createdTaskId": task.id if task else None})
    mark_export(s, "trackers", tracker.project_id)
    schedule_daily_backup(s, settings)
    faults.maybe("before_commit")
    ser = ser_todo if kind == "todo" else ser_issue
    return {
        "tracker": ser(s, tracker, local_today(settings), events=True),
        "event": {"id": event.id, "createdTaskId": event.created_task_id},
        "createdTask": {"id": task.id, "logId": log.id} if task and log else None,
        "log": {"id": log.id, "revision": log.revision, "workDate": iso_date(log.work_date)} if log else None,
    }


def complete_todo(s: Session, settings: Settings, todo_id: str, body: CompleteBody, actor_id: str) -> dict:
    t = get_or_404(s, Todo, todo_id, "To-Do")
    return _transition(s, settings, "todo", t, "completed", body.expected_revision, body.result_text,
                       body.append_to_daily_log, actor_id, OPEN_STATES["todo"])


def resolve_issue(s: Session, settings: Settings, issue_id: str, body: CompleteBody, actor_id: str) -> dict:
    i = get_or_404(s, Issue, issue_id, "Issue")
    return _transition(s, settings, "issue", i, "resolved", body.expected_revision, body.result_text,
                       body.append_to_daily_log, actor_id, OPEN_STATES["issue"])


def close_issue(s: Session, settings: Settings, issue_id: str, body: SimpleTransition, actor_id: str) -> dict:
    i = get_or_404(s, Issue, issue_id, "Issue")
    return _transition(s, settings, "issue", i, "closed", body.expected_revision, None, None, actor_id, {"resolved"})


def reopen_todo(s: Session, settings: Settings, todo_id: str, body: SimpleTransition, actor_id: str) -> dict:
    t = get_or_404(s, Todo, todo_id, "To-Do")
    return _transition(s, settings, "todo", t, "open", body.expected_revision, None, None, actor_id,
                       {"completed", "cancelled"})


def reopen_issue(s: Session, settings: Settings, issue_id: str, body: SimpleTransition, actor_id: str) -> dict:
    i = get_or_404(s, Issue, issue_id, "Issue")
    return _transition(s, settings, "issue", i, "open", body.expected_revision, None, None, actor_id, {"resolved", "closed"})


def create_response_todo(s: Session, settings: Settings, issue_id: str, body: IssueTodoCreate, actor_id: str) -> dict:
    """Issue 에서 대응 To-Do 를 만든다. Issue 상태/내용은 바꾸지 않는다(To-Do 완료가 Issue 해결이 아님)."""
    i = get_or_404(s, Issue, issue_id, "Issue")
    check_revision(i, body.expected_issue_revision, "Issue")
    return create_todo(s, settings, i.project_id, TodoCreate(content=body.content, assignee_id=body.assignee_id,
                                                              due_date=body.due_date), actor_id, source_issue_id=i.id)
