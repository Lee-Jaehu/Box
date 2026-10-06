"""업무일지. 프로젝트+작성자+날짜가 고유키이며 PUT 은 일지 전체 저장(revision 조건부)이다.

원칙
- 기존 tracker ref 는 PUT 에 누락돼도 삭제하지 않는다(읽기 전용). 숨김은 hiddenTrackerRefIds 로만.
- 새 To-Do/Issue 는 clientEntryId 로 중복 생성이 막힌다(UNIQUE(log_id, client_entry_id)).
- 이미지 상세 설명은 정식 저장 시점에 검증한다(업로드 시점이 아님).
- 파일/문서 변환은 이 트랜잭션 안에서 하지 않는다. DB 갱신만 한다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..achievements import QUALITATIVE_PRESETS, compute_quantitative
from ..config import IMAGE_MEDIA_TYPES, Settings
from ..documents import has_content, require_valid, title_preview, validate_document
from ..errors import ApiError, conflict, not_found, validation
from ..models import (Achievement, Attachment, DailyLog, Issue, LogCollaborator, LogTask, LogTrackerRef, Milestone,
                      Organization, Project, ProjectKpi, ProjectMember, TaskAttachment, Todo, User, new_id, utcnow)
from ..schemas import AchievementIn, LogSave, NewTracker, TaskIn
from .attachments import ser_attachment
from .common import audit, bump, check_revision, get_or_404, iso, iso_date, mark_export, schedule_daily_backup
from .projects import require_active_project

FieldErrors = list[dict[str, str]]


def fe(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


# ── 직렬화 ──────────────────────────────────────────────────────────────────

def _tracker_current(s: Session, ref: LogTrackerRef) -> dict:
    model = Todo if ref.tracker_type == "todo" else Issue
    t = s.get(model, ref.tracker_id)
    if t is None:
        return {"status": None, "deleted": True}
    return {"status": t.status, "assigneeId": t.assignee_id, "dueDate": iso_date(t.due_date),
            "revision": t.revision, "deleted": t.deleted_at is not None, "deletedAt": iso(t.deleted_at)}


def ser_log(s: Session, log: DailyLog) -> dict:
    tasks = []
    for t in log.tasks:
        atts = []
        for u in t.attachments:
            a = ser_attachment(u.attachment)
            atts.append({"id": u.id, "attachmentId": u.attachment_id, "title": u.title, "description": u.description,
                         "sortOrder": u.sort_order, "file": a})
        tasks.append({
            "id": t.id, "milestoneId": t.milestone_id, "milestoneSnapshot": t.milestone_snapshot, "title": t.title,
            "content": t.content_doc, "titlePreview": t.title or title_preview(t.content_doc),
            "performedStart": iso_date(t.performed_start), "performedEnd": iso_date(t.performed_end),
            "sortOrder": t.sort_order, "sourceEventId": t.source_event_id, "attachments": atts,
        })
    collabs = s.execute(select(LogCollaborator).where(LogCollaborator.log_id == log.id)).scalars().all()
    achs = s.execute(select(Achievement).where(Achievement.log_id == log.id).order_by(Achievement.sort_order)).scalars().all()
    refs = s.execute(select(LogTrackerRef).where(LogTrackerRef.log_id == log.id).order_by(LogTrackerRef.sort_order)).scalars().all()
    return {
        "id": log.id, "projectId": log.project_id, "authorId": log.author_id, "authorSnapshot": log.author_snapshot,
        "workDate": iso_date(log.work_date), "revision": log.revision, "createdAt": iso(log.created_at),
        "updatedAt": iso(log.updated_at), "deletedAt": iso(log.deleted_at),
        "lessonLearned": log.lesson_doc, "note": log.note_doc, "tasks": tasks,
        "collaborators": [{"userId": c.user_id, "name": c.name_snapshot, "team": c.team_snapshot} for c in collabs],
        "achievements": [{
            "id": a.id, "type": a.type, "presetKey": a.preset_key, "title": a.title, "content": a.content_doc,
            "numericPayload": a.numeric_payload, "kpiId": a.kpi_id, "kpiSnapshot": a.kpi_snapshot,
            "measuredOn": iso_date(a.measured_on), "periodStart": iso_date(a.period_start),
            "periodEnd": iso_date(a.period_end), "sourceTaskId": a.source_task_id,
        } for a in achs],
        # 일지는 당시 snapshot, 현재 상태는 별도 표시
        "trackerRefs": [{
            "id": r.id, "clientEntryId": r.client_entry_id, "trackerType": r.tracker_type, "trackerId": r.tracker_id,
            "originalSnapshot": r.original_snapshot, "hidden": r.hidden_at is not None,
            "current": _tracker_current(s, r),
        } for r in refs],
    }


def find_logs(s: Session, project_id: str, work_date: date | None, author_id: str | None) -> dict:
    get_or_404(s, Project, project_id, "프로젝트", include_deleted=True)
    stmt = select(DailyLog).where(DailyLog.project_id == project_id).order_by(DailyLog.work_date.desc(), DailyLog.created_at)
    if work_date:
        stmt = stmt.where(DailyLog.work_date == work_date)
    if author_id:
        stmt = stmt.where(DailyLog.author_id == author_id)
    rows = s.execute(stmt.limit(200)).scalars().all()
    # 휴지통 일지도 목록에 deletedAt 과 함께 노출해 복원 안내가 가능하도록 한다.
    return {"items": [ser_log(s, lg) for lg in rows], "nextCursor": None}


def _scoped_logs(stmt, *, project_id: str | None, author_id: str | None, team_id: str | None, division_id: str | None,
                 member_id: str | None, date_from: date | None, date_to: date | None, status: str | None = None,
                 name_query: str | None = None):
    """프로젝트 횡단 일지 조회 공통 조건. 삭제된 일지와 휴지통 프로젝트의 일지는 제외한다."""
    stmt = stmt.join(Project, Project.id == DailyLog.project_id).where(DailyLog.deleted_at.is_(None), Project.deleted_at.is_(None))
    if date_from:
        stmt = stmt.where(DailyLog.work_date >= date_from)
    if date_to:
        stmt = stmt.where(DailyLog.work_date <= date_to)
    if project_id:
        stmt = stmt.where(DailyLog.project_id == project_id)
    if author_id:
        stmt = stmt.where(DailyLog.author_id == author_id)
    if team_id:
        stmt = stmt.where(Project.team_id == team_id)
    if division_id:
        stmt = stmt.where(Project.team_id.in_(select(Organization.id).where(Organization.parent_id == division_id)))
    if status:
        stmt = stmt.where(Project.status == status)
    if name_query and name_query.strip():
        stmt = stmt.where(Project.name.like(f"%{name_query.strip()}%"))
    if member_id:  # 내가 대표이거나 참여자인 프로젝트
        stmt = stmt.where(Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == member_id)) |
                          (Project.owner_user_id == member_id))
    return stmt


def search_logs(s: Session, *, project_id: str | None = None, author_id: str | None = None, team_id: str | None = None,
                division_id: str | None = None, member_id: str | None = None, date_from: date | None = None,
                date_to: date | None = None, status: str | None = None, name_query: str | None = None, limit: int = 200) -> dict:
    stmt = _scoped_logs(select(DailyLog), project_id=project_id, author_id=author_id, team_id=team_id, division_id=division_id,
                        member_id=member_id, date_from=date_from, date_to=date_to, status=status, name_query=name_query)
    rows = s.execute(stmt.order_by(DailyLog.work_date.desc(), Project.name, DailyLog.updated_at.desc()).limit(max(1, min(limit, 500)))).scalars().all()
    items = []
    for lg in rows:
        proj = s.get(Project, lg.project_id)
        team = s.get(Organization, proj.team_id) if proj else None
        author = lg.author_snapshot or {}
        refs = s.execute(select(LogTrackerRef.tracker_type).where(LogTrackerRef.log_id == lg.id, LogTrackerRef.hidden_at.is_(None))).scalars().all()
        n_ach = s.execute(select(func.count()).select_from(Achievement).where(Achievement.log_id == lg.id)).scalar_one()
        items.append({
            "id": lg.id, "projectId": lg.project_id, "projectName": proj.name if proj else None, "projectStatus": proj.status if proj else None,
            "teamName": team.name if team else None, "authorId": lg.author_id, "authorName": author.get("name"),
            "authorTeam": author.get("teamName"), "workDate": iso_date(lg.work_date), "revision": lg.revision, "updatedAt": iso(lg.updated_at),
            "tasks": [{"id": t.id, "milestone": (t.milestone_snapshot or {}).get("name"), "title": t.title, "titlePreview": t.title or title_preview(t.content_doc), "contentPreview": title_preview(t.content_doc),
                       "attachmentCount": len(t.attachments)} for t in lg.tasks],
            "todoCount": sum(1 for r in refs if r == "todo"), "issueCount": sum(1 for r in refs if r == "issue"), "achievementCount": n_ach,
        })
    return {"items": items, "nextCursor": None}


def log_calendar(s: Session, *, date_from: date, date_to: date, **filters) -> dict:
    """달력 표시용: 날짜별 일지 수(같은 조건)."""
    stmt = _scoped_logs(select(DailyLog.work_date, func.count(DailyLog.id)), date_from=date_from, date_to=date_to,
                        project_id=filters.get("project_id"), author_id=filters.get("author_id"), team_id=filters.get("team_id"),
                        division_id=filters.get("division_id"), member_id=filters.get("member_id"), status=filters.get("status"),
                        name_query=filters.get("name_query"))
    rows = s.execute(stmt.group_by(DailyLog.work_date).order_by(DailyLog.work_date)).all()
    return {"days": [{"date": iso_date(d), "count": c} for d, c in rows]}


def get_log(s: Session, log_id: str) -> dict:
    return ser_log(s, get_or_404(s, DailyLog, log_id, "일지", include_deleted=True))


# ── 저장 ────────────────────────────────────────────────────────────────────

def _author_snapshot(s: Session, author: User, project_name: str) -> dict:
    team = s.get(Organization, author.team_id)
    return {"id": author.id, "name": author.name, "employeeNumber": author.employee_number,
            "teamId": author.team_id, "teamName": team.name if team else None, "projectName": project_name}


def _locate_log(s: Session, project_id: str, author_id: str, work_date: date) -> DailyLog | None:
    return s.execute(select(DailyLog).where(DailyLog.project_id == project_id, DailyLog.author_id == author_id,
                                            DailyLog.work_date == work_date)).scalar_one_or_none()


def _milestone_snapshot(m: Milestone) -> dict:
    return {"id": m.id, "name": m.name, "isGeneral": m.is_general}


def _normalize_doc(doc: dict | None, settings: Settings, field: str) -> dict | None:
    if doc is None:
        return None
    require_valid(doc, settings, field)
    return doc if has_content(doc["doc"]) else None


def _validate_tasks(s: Session, settings: Settings, project_id: str, log: DailyLog | None, tasks: list[TaskIn],
                    work_date: date) -> FieldErrors:
    errs: FieldErrors = []
    existing = {t.id: t for t in log.tasks} if log else {}
    seen_ids: set[str] = set()
    for i, t in enumerate(tasks):
        base = f"tasks[{i}]"
        if t.id:
            if t.id in seen_ids:
                errs.append(fe(f"{base}.id", "DUPLICATE_ID", "TASK ID가 중복됩니다."))
            seen_ids.add(t.id)
            if t.id not in existing:
                other = s.get(LogTask, t.id)
                if other is not None:
                    errs.append(fe(f"{base}.id", "ID_IN_USE", "다른 일지에서 사용 중인 TASK ID입니다."))
        m = s.get(Milestone, t.milestone_id)
        keeps_deleted = t.id in existing and existing[t.id].milestone_id == t.milestone_id
        if m is None or m.project_id != project_id or (m.deleted_at is not None and not keeps_deleted):
            errs.append(fe(f"{base}.milestoneId", "INVALID_MILESTONE", "이 프로젝트의 마일스톤을 선택해 주세요."))
        issues, use_ids = validate_document(t.content, settings, f"{base}.content")
        errs.extend(issues)
        if not issues and not has_content(t.content["doc"]):
            errs.append(fe(f"{base}.content", "REQUIRED", "TASK 내용을 입력해 주세요."))
        ps, pe = t.performed_start or work_date, t.performed_end or t.performed_start or work_date
        if pe < ps:
            errs.append(fe(f"{base}.performedEnd", "END_BEFORE_START", "종료일은 시작일보다 빠를 수 없습니다."))
        # 첨부
        by_use: dict[str, Any] = {}
        att_seen: set[str] = set()
        for j, a in enumerate(t.attachments):
            ab = f"{base}.attachments[{j}]"
            att = s.get(Attachment, a.attachment_id)
            if att is None or att.project_id != project_id:
                errs.append(fe(f"{ab}.attachmentId", "INVALID_ATTACHMENT", "이 프로젝트에 업로드된 첨부가 아닙니다."))
                continue
            if a.id:
                if a.id in att_seen:
                    errs.append(fe(f"{ab}.id", "DUPLICATE_ID", "첨부 사용처 ID가 중복됩니다."))
                att_seen.add(a.id)
                by_use[a.id] = att
                owner = s.get(TaskAttachment, a.id)
                if owner is not None and owner.task_id != (t.id or ""):
                    errs.append(fe(f"{ab}.id", "ID_IN_USE", "다른 TASK의 첨부 사용처 ID입니다."))
            if att.media_type in IMAGE_MEDIA_TYPES and not a.description.strip():
                errs.append(fe(f"{ab}.description", "IMAGE_DESCRIPTION_REQUIRED",
                               "이미지 상세 설명을 입력해 주세요. 어떤 내용을 보여주며, 보고에서 강조할 점은 무엇인가요?"))
        for use_id in use_ids:
            att = by_use.get(use_id)
            if att is None:
                errs.append(fe(f"{base}.content", "IMAGE_USE_NOT_ATTACHED", "본문 이미지가 이 TASK의 첨부로 등록되지 않았습니다."))
            elif att.media_type not in IMAGE_MEDIA_TYPES:
                errs.append(fe(f"{base}.content", "IMAGE_NODE_NOT_IMAGE", "이미지가 아닌 파일을 본문 이미지로 사용할 수 없습니다."))
    return errs


def _new_tracker_errors(s: Session, settings: Settings, project_id: str, items: list[NewTracker], prefix: str) -> FieldErrors:
    errs: FieldErrors = []
    for i, n in enumerate(items):
        issues, _ = validate_document(n.content, settings, f"{prefix}[{i}].content")
        errs.extend(issues)
        if not issues and not has_content(n.content["doc"]):
            errs.append(fe(f"{prefix}[{i}].content", "REQUIRED", "내용을 입력해 주세요."))
        if n.assignee_id:
            u = s.get(User, n.assignee_id)
            if u is None or u.deleted_at is not None:
                errs.append(fe(f"{prefix}[{i}].assigneeId", "NOT_FOUND", "담당자를 찾을 수 없습니다."))
        for fld, doc in (("impact", n.impact), ("response", n.response)):
            if doc is not None:
                errs.extend(validate_document(doc, settings, f"{prefix}[{i}].{fld}")[0])
    return errs


def _achievement_rows(s: Session, settings: Settings, project_id: str, items: list[AchievementIn],
                      task_ids: set[str]) -> tuple[list[dict], FieldErrors]:
    rows: list[dict] = []
    errs: FieldErrors = []
    for i, a in enumerate(items):
        base = f"achievements[{i}]"
        try:
            kpi = None
            if a.kpi_id:
                kpi = s.get(ProjectKpi, a.kpi_id)
                if a.type != "quantitative":
                    raise validation("정성 성과는 KPI에 연결할 수 없습니다.", [fe(f"{base}.kpiId", "QUALITATIVE_KPI", "정량 KPI만 연결할 수 있습니다.")])
                if kpi is None or kpi.project_id != project_id or kpi.deleted_at is not None:
                    raise validation("KPI를 찾을 수 없습니다.", [fe(f"{base}.kpiId", "NOT_FOUND", "이 프로젝트의 KPI가 아닙니다.")])
            if a.period_start and a.period_end and a.period_end < a.period_start:
                raise validation("대상 기간이 올바르지 않습니다.", [fe(f"{base}.periodEnd", "END_BEFORE_START", "종료일이 시작일보다 빠릅니다.")])
            if a.source_task_id and a.source_task_id not in task_ids:
                raise validation("원본 TASK를 찾을 수 없습니다.", [fe(f"{base}.sourceTaskId", "NOT_FOUND", "이 일지의 TASK가 아닙니다.")])
            content = None
            payload = None
            if a.type == "quantitative":
                raw = dict(a.numeric_payload or {})
                raw.pop("derived", None)  # 클라이언트 계산값은 신뢰하지 않는다.
                if kpi is not None and kpi.direction and "direction" not in raw:
                    raw["direction"] = kpi.direction
                payload = compute_quantitative(a.preset_key, raw, f"{base}.numericPayload")
                if a.content is not None:
                    require_valid(a.content, settings, f"{base}.content")
                    content = a.content
            else:
                if a.preset_key not in QUALITATIVE_PRESETS:
                    raise validation("알 수 없는 정성 프리셋입니다.", [fe(f"{base}.presetKey", "UNKNOWN_PRESET", a.preset_key)])
                if a.content is None:
                    raise validation("정성 성과 내용이 필요합니다.", [fe(f"{base}.content", "REQUIRED", "내용을 입력해 주세요.")])
                require_valid(a.content, settings, f"{base}.content")
                if not has_content(a.content["doc"]):
                    raise validation("정성 성과 내용이 필요합니다.", [fe(f"{base}.content", "REQUIRED", "내용을 입력해 주세요.")])
                content = a.content
            rows.append({
                "id": a.id or new_id(), "type": a.type, "preset_key": a.preset_key, "title": a.title,
                "content_doc": content, "numeric_payload": payload, "kpi_id": a.kpi_id,
                "kpi_snapshot": ({"id": kpi.id, "name": kpi.name, "unit": kpi.unit, "baselineValue": kpi.baseline_value,
                                  "targetValue": kpi.target_value, "direction": kpi.direction} if kpi else None),
                "measured_on": a.measured_on, "period_start": a.period_start, "period_end": a.period_end,
                "source_task_id": a.source_task_id, "sort_order": i,
            })
        except ApiError as e:
            errs.extend(e.field_errors or [fe(base, e.code, e.message)])
    return rows, errs


def _make_tracker(s: Session, model: type, project_id: str, log: DailyLog, n: NewTracker, actor_id: str):
    t = model(project_id=project_id, content_doc=n.content, assignee_id=n.assignee_id, due_date=n.due_date,
              source_log_id=log.id, status="open")
    if model is Issue:
        t.impact_doc, t.response_doc = n.impact, n.response
    t.created_by = t.updated_by = actor_id
    s.add(t)
    s.flush()
    return t


def save_log(s: Session, settings: Settings, project_id: str, work_date: date, author_id: str, body: LogSave,
             actor_id: str) -> dict:
    project = require_active_project(s, project_id)
    author = s.get(User, author_id)
    if author is None or author.deleted_at is not None:
        raise validation("작성자를 찾을 수 없습니다.", [fe("authorId", "NOT_FOUND", "작성자를 선택해 주세요.")])

    log = _locate_log(s, project_id, author_id, work_date)
    if log is None:
        if body.expected_revision != 0:
            raise not_found("일지")
    elif log.deleted_at is not None:
        raise conflict("LOG_IN_TRASH", "같은 날짜의 일지가 휴지통에 있습니다. 복원해서 이어 작성해 주세요.", resource_id=log.id,
                       current_revision=log.revision)
    elif body.expected_revision == 0:
        raise conflict("LOG_EXISTS", "같은 날짜의 일지가 이미 있습니다. 불러와서 이어 작성해 주세요.", resource_id=log.id,
                       current_revision=log.revision)
    else:
        check_revision(log, body.expected_revision, "일지")

    # ── 검증 (변경 전에 모두 모은다) ──
    errs = _validate_tasks(s, settings, project_id, log, body.tasks, work_date)
    entry_ids = [n.client_entry_id for n in (*body.new_todos, *body.new_issues)]
    if len(entry_ids) != len(set(entry_ids)):
        errs.append(fe("newTodos", "DUPLICATE_ID", "clientEntryId가 중복됩니다."))
    errs.extend(_new_tracker_errors(s, settings, project_id, body.new_todos, "newTodos"))
    errs.extend(_new_tracker_errors(s, settings, project_id, body.new_issues, "newIssues"))
    lesson = note = None
    for fld, doc in (("lessonLearned", body.lesson_learned), ("note", body.note)):
        try:
            norm = _normalize_doc(doc, settings, fld)
        except ApiError as e:
            errs.extend(e.field_errors or [])
            norm = None
        if fld == "lessonLearned":
            lesson = norm
        else:
            note = norm
    task_ids = {t.id for t in body.tasks if t.id}
    ach_rows, ach_errs = _achievement_rows(s, settings, project_id, body.achievements, task_ids)
    errs.extend(ach_errs)
    collab_users: list[User] = []
    for i, uid in enumerate(dict.fromkeys(body.collaborator_ids)):
        u = s.get(User, uid)
        if u is None or u.deleted_at is not None:
            errs.append(fe(f"collaboratorIds[{i}]", "NOT_FOUND", "협업자를 찾을 수 없습니다."))
        else:
            collab_users.append(u)
    if errs:
        raise ApiError(422, "VALIDATION_ERROR", "입력 내용을 확인해 주세요.", field_errors=errs)

    has_any = bool(body.tasks or body.new_todos or body.new_issues or body.achievements or lesson or note or collab_users)
    if not has_any and (log is None or not log.tasks):
        raise validation("저장할 내용이 없습니다. TASK 또는 다른 기록을 하나 이상 입력해 주세요.",
                         [fe("tasks", "EMPTY_LOG", "기록이 비어 있습니다.")])

    # ── 변경 ──
    created = log is None
    if created:
        log = DailyLog(project_id=project_id, author_id=author_id, work_date=work_date, revision=1,
                       author_snapshot=_author_snapshot(s, author, project.name))
        log.created_by = log.updated_by = actor_id
        s.add(log)
        try:
            s.flush()
        except IntegrityError:  # BEGIN IMMEDIATE 로 경쟁은 이미 직렬화되지만 unique 제약이 마지막 방어선이다.
            raise conflict("LOG_EXISTS", "같은 날짜의 일지가 이미 있습니다. 불러와서 이어 작성해 주세요.") from None
    log.lesson_doc, log.note_doc = lesson, note

    existing = {t.id: t for t in log.tasks}
    keep: set[str] = set()
    for order, t in enumerate(body.tasks):
        row = existing.get(t.id) if t.id else None
        m = s.get(Milestone, t.milestone_id)
        if row is None:
            row = LogTask(id=t.id or new_id(), log_id=log.id, milestone_id=m.id, milestone_snapshot=_milestone_snapshot(m),
                          content_doc=t.content)
            s.add(row)
            log.tasks.append(row)
        else:
            row.content_doc = t.content
            if row.milestone_id != m.id:  # 마일스톤을 명시적으로 바꾼 경우에만 snapshot 갱신
                row.milestone_id, row.milestone_snapshot = m.id, _milestone_snapshot(m)
        row.title = (t.title or "").strip() or None
        row.performed_start = t.performed_start or work_date
        row.performed_end = t.performed_end or t.performed_start or work_date
        row.sort_order = order
        row.updated_at = utcnow()
        keep.add(row.id)
        s.flush()
        _sync_attachments(s, row, t)
    for tid, row in existing.items():
        if tid not in keep:
            log.tasks.remove(row)
            s.delete(row)

    s.query(LogCollaborator).filter(LogCollaborator.log_id == log.id).delete()
    for u in collab_users:
        team = s.get(Organization, u.team_id)
        s.add(LogCollaborator(log_id=log.id, user_id=u.id, name_snapshot=u.name, team_snapshot=team.name if team else None))
    s.query(Achievement).filter(Achievement.log_id == log.id).delete()
    for r in ach_rows:
        s.add(Achievement(log_id=log.id, **r))

    # 트래커: 기존 ref 는 건드리지 않는다. 숨김만 반영.
    refs = {r.id: r for r in s.execute(select(LogTrackerRef).where(LogTrackerRef.log_id == log.id)).scalars()}
    for rid in body.hidden_tracker_ref_ids:
        if rid not in refs:
            raise validation("숨길 항목을 찾을 수 없습니다.", [fe("hiddenTrackerRefIds", "NOT_FOUND", rid)])
        if refs[rid].hidden_at is None:
            refs[rid].hidden_at = utcnow()
    by_entry = {r.client_entry_id: r for r in refs.values()}
    ref_map: dict[str, dict] = {}
    next_order = max([r.sort_order for r in refs.values()], default=-1) + 1
    created_tracker = False
    for kind, model, items in (("todo", Todo, body.new_todos), ("issue", Issue, body.new_issues)):
        for n in items:
            ref = by_entry.get(n.client_entry_id)
            if ref is None:
                t = _make_tracker(s, model, project_id, log, n, actor_id)
                a = s.get(User, n.assignee_id) if n.assignee_id else None
                ref = LogTrackerRef(log_id=log.id, client_entry_id=n.client_entry_id, tracker_type=kind, tracker_id=t.id,
                                    sort_order=next_order, original_snapshot={
                                        "content": n.content, "status": "open", "assigneeId": n.assignee_id, "assigneeName": a.name if a else None,
                                        "dueDate": iso_date(n.due_date), "impact": n.impact, "response": n.response,
                                        "registeredAt": iso(utcnow())})
                next_order += 1
                s.add(ref)
                created_tracker = True
                audit(s, f"{kind}.create", kind, t.id, actor_id, {"sourceLogId": log.id})
            ref_map[n.client_entry_id] = {"refId": ref.id, "trackerType": ref.tracker_type, "trackerId": ref.tracker_id}
    s.flush()

    if not created:
        bump(log, actor_id)
    s.flush()
    s.refresh(log)
    audit(s, "log.create" if created else "log.update", "log", log.id, actor_id, {"revision": log.revision})
    mark_export(s, "daily", project_id, work_date)
    if created_tracker:
        mark_export(s, "trackers", project_id)
    schedule_daily_backup(s, settings)
    out = ser_log(s, log)
    out["trackerRefMap"] = ref_map
    return out


def _sync_attachments(s: Session, row: LogTask, t: TaskIn) -> None:
    current = {u.id: u for u in row.attachments}
    keep: set[str] = set()
    for order, a in enumerate(t.attachments):
        use = current.get(a.id) if a.id else None
        att = s.get(Attachment, a.attachment_id)
        if use is None:
            use = TaskAttachment(id=a.id or new_id(), task_id=row.id, attachment_id=att.id)
            s.add(use)
            row.attachments.append(use)
        use.attachment_id = att.id
        use.title = (a.title or None)
        use.description = a.description.strip()
        use.sort_order = order
        att.state = "committed"
        keep.add(use.id)
    s.flush()
    for uid, use in current.items():
        if uid not in keep:
            row.attachments.remove(use)
            s.delete(use)


# ── tracker 완료 결과를 일지 TASK 로 추가 ───────────────────────────────────

def append_result_task(s: Session, settings: Settings, project_id: str, author_id: str, work_date: date,
                       milestone_id: str, content_doc: dict, expected_log_revision: int, actor_id: str,
                       source_event_id: str) -> tuple[LogTask, DailyLog]:
    project = require_active_project(s, project_id)
    author = s.get(User, author_id)
    if author is None or author.deleted_at is not None:
        raise validation("작성자를 찾을 수 없습니다.", [fe("appendToDailyLog.authorId", "NOT_FOUND", "작성자")])
    m = s.get(Milestone, milestone_id)
    if m is None or m.project_id != project_id or m.deleted_at is not None:
        raise validation("마일스톤을 선택해 주세요.", [fe("appendToDailyLog.milestoneId", "INVALID_MILESTONE", "이 프로젝트의 마일스톤")])
    log = _locate_log(s, project_id, author_id, work_date)
    if log is None:
        if expected_log_revision != 0:
            raise not_found("일지")
        log = DailyLog(project_id=project_id, author_id=author_id, work_date=work_date, revision=1,
                       author_snapshot=_author_snapshot(s, author, project.name))
        log.created_by = log.updated_by = actor_id
        s.add(log)
        try:
            s.flush()
        except IntegrityError:
            raise conflict("LOG_EXISTS", "같은 날짜의 일지가 이미 있습니다.") from None
    elif log.deleted_at is not None:
        raise conflict("LOG_IN_TRASH", "같은 날짜의 일지가 휴지통에 있습니다.", resource_id=log.id)
    else:
        if expected_log_revision == 0:
            raise conflict("LOG_EXISTS", "같은 날짜의 일지가 이미 있습니다. 최신 일지 revision으로 다시 시도해 주세요.",
                           resource_id=log.id, current_revision=log.revision)
        check_revision(log, expected_log_revision, "일지")
        bump(log, actor_id)
    task = LogTask(log_id=log.id, milestone_id=m.id, milestone_snapshot=_milestone_snapshot(m), content_doc=content_doc,
                   performed_start=work_date, performed_end=work_date,
                   sort_order=max([t.sort_order for t in log.tasks], default=-1) + 1, source_event_id=source_event_id)
    s.add(task)
    log.tasks.append(task)
    s.flush()
    mark_export(s, "daily", project_id, work_date)
    return task, log


def delete_log(s: Session, log_id: str, expected_revision: int, actor_id: str) -> dict:
    log = get_or_404(s, DailyLog, log_id, "일지")
    require_active_project(s, log.project_id)
    check_revision(log, expected_revision, "일지")
    log.deleted_at = utcnow()
    bump(log, actor_id)
    audit(s, "log.delete", "log", log.id, actor_id)
    mark_export(s, "daily", log.project_id, log.work_date)  # 마지막 기록이 사라져도 빈 logs 로 교체
    return {"id": log.id, "deletedAt": iso(log.deleted_at), "revision": log.revision}
