"""JSON 사본 exporter. SQLite 가 원본이고 data/json 은 단방향 자동 사본이다(사본 → DB 반영 없음).

처리 순서(대상 target 하나):
  1) 짧은 읽기 트랜잭션에서 데이터와 sourceRevision(requested_revision)을 함께 취득하고 읽기를 끝낸다.
  2) DB 밖에서 JSON 직렬화 → 같은 폴더 임시 파일 flush/fsync → os.replace.
  3) 쓰기 트랜잭션에서 exported_revision = 1)에서 취득한 revision 으로만 표시. 그 사이 더 큰 revision 이
     요청됐다면 pending 으로 남긴다. 프로세스가 교체 직후 종료돼도 같은 내용을 다시 내보내는 것은 안전하다.
실패는 attempts/last_error/next_attempt_at(backoff) 에 기록하고, 이미 commit 된 업무 저장은 취소하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import faults
from ..config import Settings
from ..models import (Achievement, DailyLog, ExportJob, Issue, LogCollaborator, LogTrackerRef, Milestone,
                      Organization, Project, ProjectKpi, ProjectMember, Todo, TrackerEvent, User, utcnow)
from .common import iso_date, mark_export
from .attachments import attachment_abs_path

SCHEMA_VERSION = "1.0"
MAX_BACKOFF_SECONDS = 300


def _kst(settings: Settings, dt: datetime | None) -> str | None:
    return dt.astimezone(ZoneInfo(settings.timezone)).isoformat(timespec="seconds") if dt else None


def _header(settings: Settings, file_type: str, revision: int, with_doc_version: bool = False) -> dict:
    h: dict[str, Any] = {"fileType": file_type, "schemaVersion": SCHEMA_VERSION}
    if with_doc_version:
        h["documentVersion"] = 1
    h.update(generatedAt=_kst(settings, utcnow()), sourceRevision=revision, timezone=settings.timezone)
    return h


# ── payload 빌더 (읽기 전용) ────────────────────────────────────────────────

def _user_brief(s: Session, u: User | None) -> dict | None:
    if u is None:
        return None
    team = s.get(Organization, u.team_id)
    return {"id": u.id, "name": u.name, "employeeNumber": u.employee_number, "teamId": u.team_id,
            "teamName": team.name if team else None}


def build_master(s: Session, settings: Settings, revision: int) -> list[tuple[str, dict]]:
    orgs = s.execute(select(Organization).order_by(Organization.kind, Organization.name, Organization.id)).scalars().all()
    users = s.execute(select(User).order_by(User.name, User.id)).scalars().all()
    return [
        ("master/organizations.json", {**_header(settings, "WORKLOG_MASTER_EXPORT", revision), "kind": "organizations", "items": [
            {"id": o.id, "name": o.name, "kind": o.kind, "parentId": o.parent_id, "externalKey": o.external_key,
             "active": o.active, "deletedAt": _kst(settings, o.deleted_at)} for o in orgs]}),
        ("master/users.json", {**_header(settings, "WORKLOG_MASTER_EXPORT", revision), "kind": "users", "items": [
            {"id": u.id, "name": u.name, "teamId": u.team_id, "employeeNumber": u.employee_number,
             "externalKey": u.external_key, "active": u.active, "deletedAt": _kst(settings, u.deleted_at)} for u in users]}),
    ]


def build_project(s: Session, settings: Settings, project_id: str, revision: int) -> list[tuple[str, dict]]:
    p = s.get(Project, project_id)
    if p is None:
        return []
    team = s.get(Organization, p.team_id)
    parent = s.get(Organization, team.parent_id) if team and team.parent_id else None
    owner = s.get(User, p.owner_user_id)
    members = [s.get(User, uid) for uid in s.execute(select(ProjectMember.user_id).where(ProjectMember.project_id == p.id)).scalars()]
    ms = s.execute(select(Milestone).where(Milestone.project_id == p.id).order_by(Milestone.is_general.desc(), Milestone.sort_order, Milestone.id)).scalars().all()
    ks = s.execute(select(ProjectKpi).where(ProjectKpi.project_id == p.id).order_by(ProjectKpi.created_at, ProjectKpi.id)).scalars().all()
    body = {
        **_header(settings, "WORKLOG_PROJECT_EXPORT", revision),
        "project": {
            "id": p.id, "name": p.name, "revision": p.revision, "deletedAt": _kst(settings, p.deleted_at),
            "isShortTerm": p.is_short_term, "status": p.status,
            "team": {"id": team.id, "name": team.name, "parent": {"id": parent.id, "name": parent.name} if parent else None} if team else None,
            "owner": _user_brief(s, owner),
            "members": [{"id": m.id, "name": m.name} for m in members if m],
            "startDate": iso_date(p.start_date), "endDate": iso_date(p.end_date),
            "background": p.background_doc, "purpose": p.purpose_doc, "retrospective": p.retrospective_doc,
        },
        "milestones": [{
            "id": m.id, "name": m.name, "isGeneral": m.is_general, "status": m.status, "sortOrder": m.sort_order,
            "plannedStart": iso_date(m.planned_start), "plannedEnd": iso_date(m.planned_end),
            "baselineStart": iso_date(m.baseline_start), "baselineEnd": iso_date(m.baseline_end),
            "baselineConfirmedAt": _kst(settings, m.baseline_confirmed_at),
            "actualStart": iso_date(m.actual_start), "actualEnd": iso_date(m.actual_end),
            "deletedAt": _kst(settings, m.deleted_at)} for m in ms],
        "kpis": [{"id": k.id, "name": k.name, "unit": k.unit, "baselineValue": k.baseline_value, "targetValue": k.target_value,
                  "direction": k.direction, "active": k.active, "deletedAt": _kst(settings, k.deleted_at)} for k in ks],
    }
    return [(f"projects/{project_id}/project.json", body)]


def _export_log(s: Session, settings: Settings, lg: DailyLog) -> dict:
    snap = lg.author_snapshot or {}
    refs = s.execute(select(LogTrackerRef).where(LogTrackerRef.log_id == lg.id, LogTrackerRef.hidden_at.is_(None))
                     .order_by(LogTrackerRef.sort_order)).scalars().all()

    def rec(r: LogTrackerRef) -> dict:
        return {"refId": r.id, "trackerId": r.tracker_id, "clientEntryId": r.client_entry_id,
                "originalSnapshot": r.original_snapshot}

    tasks = []
    for t in lg.tasks:
        ms = t.milestone_snapshot or {}
        tasks.append({
            "id": t.id, "title": t.title, "milestone": {"id": ms.get("id"), "nameSnapshot": ms.get("name")},
            "performedStart": iso_date(t.performed_start), "performedEnd": iso_date(t.performed_end),
            "sortOrder": t.sort_order, "content": t.content_doc,
            "attachments": [{
                "useId": u.id, "attachmentId": u.attachment_id, "taskId": t.id, "originalName": u.attachment.original_name,
                "mediaType": u.attachment.media_type, "sizeBytes": u.attachment.size_bytes,
                "width": u.attachment.width, "height": u.attachment.height, "title": u.title, "description": u.description,
                "sortOrder": u.sort_order, "fileRef": f"attachments/{u.attachment.stored_relative_path}"} for u in t.attachments],
        })
    achs = s.execute(select(Achievement).where(Achievement.log_id == lg.id).order_by(Achievement.sort_order)).scalars().all()
    collabs = s.execute(select(LogCollaborator).where(LogCollaborator.log_id == lg.id)).scalars().all()
    return {
        "createdAt": _kst(settings, lg.created_at), "updatedAt": _kst(settings, lg.updated_at),
        "todoRecords": [rec(r) for r in refs if r.tracker_type == "todo"],
        "issueRecords": [rec(r) for r in refs if r.tracker_type == "issue"],
        "achievements": [{
            "id": a.id, "type": a.type, "presetKey": a.preset_key, "title": a.title, "kpiId": a.kpi_id,
            "kpiSnapshot": a.kpi_snapshot, "measuredOn": iso_date(a.measured_on), "periodStart": iso_date(a.period_start),
            "periodEnd": iso_date(a.period_end), "numericPayload": a.numeric_payload, "content": a.content_doc,
            "sourceTaskId": a.source_task_id} for a in achs],
        "lessonLearned": lg.lesson_doc, "note": lg.note_doc,
        "collaborators": [{"userId": c.user_id, "name": c.name_snapshot, "team": c.team_snapshot} for c in collabs],
        "id": lg.id, "revision": lg.revision,
        "author": {k: snap.get(k) for k in ("id", "name", "employeeNumber", "teamId", "teamName")},
        "tasks": tasks,
    }


def build_daily(s: Session, settings: Settings, project_id: str, work_date, revision: int) -> list[tuple[str, dict]]:
    p = s.get(Project, project_id)
    if p is None:
        return []
    logs = s.execute(select(DailyLog).where(DailyLog.project_id == project_id, DailyLog.work_date == work_date,
                                            DailyLog.deleted_at.is_(None)).order_by(DailyLog.created_at, DailyLog.id)).scalars().all()
    # 작성자 이름순으로 안정 정렬
    logs = sorted(logs, key=lambda x: ((x.author_snapshot or {}).get("name") or "", x.id))
    body = {**_header(settings, "WORKLOG_DAILY_EXPORT", revision, with_doc_version=True),
            "project": {"id": p.id, "name": p.name, "deletedAt": _kst(settings, p.deleted_at)},
            "date": iso_date(work_date), "logs": [_export_log(s, settings, lg) for lg in logs]}  # 빈 날짜도 logs=[] 로 교체
    return [(f"projects/{project_id}/{iso_date(work_date)}/daily.json", body)]


def build_trackers(s: Session, settings: Settings, project_id: str, revision: int) -> list[tuple[str, dict]]:
    p = s.get(Project, project_id)
    if p is None:
        return []
    todos = s.execute(select(Todo).where(Todo.project_id == project_id).order_by(Todo.created_at, Todo.id)).scalars().all()
    issues = s.execute(select(Issue).where(Issue.project_id == project_id).order_by(Issue.created_at, Issue.id)).scalars().all()
    ids = [t.id for t in todos] + [i.id for i in issues]
    events = s.execute(select(TrackerEvent).where(TrackerEvent.tracker_id.in_(ids)).order_by(TrackerEvent.occurred_at, TrackerEvent.id)).scalars().all() if ids else []
    body = {
        **_header(settings, "WORKLOG_TRACKER_EXPORT", revision), "projectId": project_id,
        "projectDeletedAt": _kst(settings, p.deleted_at),
        "todos": [{"id": t.id, "content": t.content_doc, "assigneeId": t.assignee_id, "dueDate": iso_date(t.due_date),
                   "status": t.status, "sourceLogId": t.source_log_id, "sourceIssueId": t.source_issue_id,
                   "revision": t.revision, "deletedAt": _kst(settings, t.deleted_at)} for t in todos],
        "issues": [{"id": i.id, "content": i.content_doc, "assigneeId": i.assignee_id, "dueDate": iso_date(i.due_date),
                    "impact": i.impact_doc, "response": i.response_doc, "status": i.status, "sourceLogId": i.source_log_id,
                    "revision": i.revision, "deletedAt": _kst(settings, i.deleted_at)} for i in issues],
        "events": [{"id": e.id, "trackerType": e.tracker_type, "trackerId": e.tracker_id, "previousStatus": e.previous_status,
                    "nextStatus": e.next_status, "resultText": e.result_text, "actorId": e.actor_id,
                    "occurredAt": _kst(settings, e.occurred_at), "createdTaskId": e.created_task_id} for e in events],
    }
    return [(f"projects/{project_id}/trackers.json", body)]


def build_for_job(s: Session, settings: Settings, job: ExportJob, revision: int) -> list[tuple[str, dict]]:
    if job.kind == "master":
        return build_master(s, settings, revision)
    if job.kind == "project":
        return build_project(s, settings, job.project_id, revision)  # type: ignore[arg-type]
    if job.kind == "trackers":
        return build_trackers(s, settings, job.project_id, revision)  # type: ignore[arg-type]
    return build_daily(s, settings, job.project_id, job.work_date, revision)  # type: ignore[arg-type]


# ── 파일 쓰기 ───────────────────────────────────────────────────────────────

def write_json_atomic(path: Path, payload: dict) -> None:
    """UTF-8, ensure_ascii=False, indent=2, stable ordering. 같은 폴더 임시 파일 → fsync → replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        faults.maybe("export_before_replace")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)  # 실패해도 이전 정상 사본은 그대로 남는다
        raise


# ── 작업 처리 ───────────────────────────────────────────────────────────────

def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2 ** min(attempts, 8), MAX_BACKOFF_SECONDS))


def export_target(read_factory: sessionmaker[Session], write_factory: sessionmaker[Session], settings: Settings,
                  target_key: str) -> bool:
    """대상 하나를 내보낸다. 성공(또는 이미 최신)이면 True."""
    rs = read_factory()
    try:
        job = rs.get(ExportJob, target_key)
        if job is None:
            return True
        revision = job.requested_revision
        files = build_for_job(rs, settings, job, revision)
    finally:
        rs.close()  # 읽기 트랜잭션 종료 후 파일 작업
    try:
        for rel, payload in files:
            write_json_atomic(settings.json_dir / rel, payload)
        faults.maybe("export_after_replace")
    except BaseException as e:  # noqa: BLE001
        ws = write_factory()
        try:
            j = ws.get(ExportJob, target_key)
            if j is not None:
                j.attempts += 1
                j.status = "failed"
                j.last_error = f"{type(e).__name__}: {e}"[:500]
                j.next_attempt_at = utcnow() + _backoff(j.attempts)
                j.updated_at = utcnow()
            ws.commit()
        finally:
            ws.close()
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return False
    ws = write_factory()
    try:
        j = ws.get(ExportJob, target_key)
        if j is not None:
            j.exported_revision = max(j.exported_revision, revision)
            j.status = "done" if j.requested_revision == j.exported_revision else "pending"
            j.attempts = 0
            j.last_error = None
            j.next_attempt_at = None
            j.updated_at = utcnow()
        ws.commit()
    finally:
        ws.close()
    return True


def pending_targets(read_factory: sessionmaker[Session], limit: int = 50, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    rs = read_factory()
    try:
        rows = rs.execute(select(ExportJob).where(ExportJob.status.in_(("pending", "failed"))).order_by(ExportJob.updated_at)).scalars().all()
        return [j.target_key for j in rows if j.next_attempt_at is None or j.next_attempt_at <= now][:limit]
    finally:
        rs.close()


def process_pending(read_factory: sessionmaker[Session], write_factory: sessionmaker[Session], settings: Settings,
                    limit: int = 50) -> int:
    n = 0
    for key in pending_targets(read_factory, limit):
        export_target(read_factory, write_factory, settings, key)
        n += 1
    return n


# ── 상태 / 재생성 / bundle ──────────────────────────────────────────────────

def export_status(s: Session, settings: Settings, project_id: str | None) -> dict:
    stmt = select(ExportJob).order_by(ExportJob.target_key)
    if project_id:
        stmt = stmt.where((ExportJob.project_id == project_id) | (ExportJob.kind == "master"))
    jobs = s.execute(stmt).scalars().all()
    names = {p.id: p.name for p in s.execute(select(Project)).scalars()}

    def rel(j: ExportJob) -> str:  # data\json 기준 상대 경로(실제 파일 위치)
        if j.kind == "master":
            return "master/organizations.json, master/users.json"
        base = f"projects/{j.project_id}"
        return {"project": f"{base}/project.json", "trackers": f"{base}/trackers.json",
                "daily": f"{base}/{iso_date(j.work_date)}/daily.json"}[j.kind]

    items = [{"targetKey": j.target_key, "kind": j.kind, "projectId": j.project_id, "projectName": names.get(j.project_id or ""),
              "date": iso_date(j.work_date), "relativePath": rel(j),
              "requestedRevision": j.requested_revision, "exportedRevision": j.exported_revision, "status": j.status,
              "attempts": j.attempts, "lastError": j.last_error, "nextAttemptAt": _kst(settings, j.next_attempt_at),
              "updatedAt": _kst(settings, j.updated_at),
              "lagging": j.exported_revision < j.requested_revision} for j in jobs]
    return {"items": items, "jsonDir": str(settings.json_dir), "dailyCount": sum(1 for i in items if i["kind"] == "daily"),
            "pendingCount": sum(1 for i in items if i["lagging"]),
            "failedCount": sum(1 for i in items if i["status"] == "failed")}


def request_rebuild(s: Session, project_id: str | None, everything: bool) -> int:
    n = 0
    if everything or project_id is None:
        mark_export(s, "master")
        n += 1
    pids = [p for p in s.execute(select(Project.id)).scalars()] if everything or project_id is None else [project_id]
    for pid in pids:
        mark_export(s, "project", pid)
        mark_export(s, "trackers", pid)
        n += 2
        dates = {d for d in s.execute(select(DailyLog.work_date).where(DailyLog.project_id == pid)).scalars()}
        for d in sorted(dates):
            mark_export(s, "daily", pid, d)
            n += 1
    return n


def build_bundle(read_factory: sessionmaker[Session], settings: Settings, project_id: str, date_from, date_to,
                 include_attachments: bool) -> dict:
    """DB 의 일관된 snapshot 에서 전달용 bundle(zip)을 만든다. 자동 사본 파일을 묶지 않는다."""
    rs = read_factory()
    try:
        p = rs.get(Project, project_id)
        if p is None or p.deleted_at is not None:  # 삭제 프로젝트는 보고용 bundle 에서 제외
            return {"error": "PROJECT_NOT_AVAILABLE"}
        stmt = select(DailyLog.work_date).where(DailyLog.project_id == project_id, DailyLog.deleted_at.is_(None))
        if date_from:
            stmt = stmt.where(DailyLog.work_date >= date_from)
        if date_to:
            stmt = stmt.where(DailyLog.work_date <= date_to)
        dates = sorted(set(rs.execute(stmt).scalars()))
        files = build_project(rs, settings, project_id, 0) + build_trackers(rs, settings, project_id, 0)
        for d in dates:
            files += build_daily(rs, settings, project_id, d, 0)
        att_rows = []
        if include_attachments:
            for _, payload in files:
                for lg in payload.get("logs", []):
                    for t in lg["tasks"]:
                        att_rows.extend(t["attachments"])
    finally:
        rs.close()
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = settings.exports_dir / f"bundle-{project_id[:8]}-{stamp}.zip"
    manifest: dict[str, Any] = {"fileType": "WORKLOG_BUNDLE_MANIFEST", "schemaVersion": SCHEMA_VERSION,
                                "generatedAt": _kst(settings, utcnow()), "projectId": project_id, "files": [], "attachments": [],
                                "missingAttachments": []}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, payload in files:
            blob = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            z.writestr(rel, blob)
            manifest["files"].append({"path": rel, "sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)})
        for a in {a["fileRef"]: a for a in att_rows}.values():
            rel = a["fileRef"].split("attachments/", 1)[1]
            src = attachment_abs_path(settings, rel)
            if not src.exists():
                manifest["missingAttachments"].append(a["fileRef"])
                continue
            z.write(src, a["fileRef"])
            manifest["attachments"].append({"path": a["fileRef"], "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "size": src.stat().st_size})
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"path": out.name, "manifest": manifest}
