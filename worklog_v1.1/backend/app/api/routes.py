"""REST 라우트 (/api/v1). 얇은 계층: 요청 검증 → mutate/read 헬퍼 → 서비스 호출."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import select

from ..config import IMAGE_MEDIA_TYPES
from ..errors import ApiError, not_found, validation
from ..migrate import head_revision
from ..models import Attachment, BackupRun, new_id
from ..runtime import instance_info
from .. import schemas as sc
from ..services import attachments as att_svc
from ..services import backups as backup_svc
from ..services import exports as export_svc
from ..services import imports as import_svc
from ..services import logs as log_svc
from ..services import masters as master_svc
from ..services import projects as proj_svc
from ..services import trackers as trk_svc
from ..services import trash as trash_svc
from ..services.common import load_actor
from .common import mutate, read, request_id, rt_of

router = APIRouter(prefix="/api/v1")

Limit = Annotated[int, Query(ge=1, le=200)]


def _json(code: int, body: dict) -> JSONResponse:
    return JSONResponse(status_code=code, content=body)


def _m(request: Request, body, fn, *, actor_required: bool = True, status_code: int = 200, extra: dict | None = None):
    payload = body.model_dump(mode="json") if hasattr(body, "model_dump") else body
    if extra:
        payload = {"_": extra, "body": payload}
    code, resp = mutate(request, payload, fn, actor_required=actor_required, status_code=status_code)
    return _json(code, resp)


# ── 상태 ────────────────────────────────────────────────────────────────────

@router.get("/health")
def health(request: Request):
    rt = rt_of(request)
    with rt.read_factory() as s:
        s.execute(select(1))
    return {"status": "ok", "maintenance": rt.maintenance}


@router.get("/app-info")
def app_info(request: Request):
    rt = rt_of(request)
    info = instance_info(rt)
    return {"data": {**info, "schemaVersion": head_revision(), "timezone": rt.settings.timezone,
                     "maxAttachmentBytes": rt.settings.max_attachment_bytes,
                     "features": ["logs", "trackers", "imports", "exports", "backups", "reports"]},
            "meta": {"requestId": request_id(request)}}


# ── 조직/사용자 ─────────────────────────────────────────────────────────────

@router.get("/organizations")
def list_orgs(request: Request, kind: str | None = None, includeInactive: bool = True, limit: Limit = 200, cursor: str | None = None):
    return read(request, lambda s: master_svc.list_orgs(s, kind, includeInactive, limit, cursor))


@router.post("/organizations")
def create_org(request: Request, body: sc.OrgCreate):
    return _m(request, body, lambda s, a: master_svc.create_org(s, body, a), actor_required=False, status_code=201)


@router.patch("/organizations/{org_id}")
def patch_org(request: Request, org_id: str, body: sc.OrgPatch):
    return _m(request, body, lambda s, a: master_svc.patch_org(s, org_id, body, a), actor_required=False)


@router.get("/users")
def list_users(request: Request, teamId: str | None = None, divisionId: str | None = None, active: bool | None = None,
               q: str | None = None, limit: Limit = 200, cursor: str | None = None):
    return read(request, lambda s: master_svc.list_users(s, teamId, divisionId, active, q, limit, cursor))


@router.post("/users")
def create_user(request: Request, body: sc.UserCreate):
    return _m(request, body, lambda s, a: master_svc.create_user(s, body, a), actor_required=False, status_code=201)


@router.patch("/users/{user_id}")
def patch_user(request: Request, user_id: str, body: sc.UserPatch):
    return _m(request, body, lambda s, a: master_svc.patch_user(s, user_id, body, a), actor_required=False)


# ── 가져오기 ────────────────────────────────────────────────────────────────

@router.get("/imports/masters/template")
def import_template(entity: str = "workbook", format: str = "xlsx"):
    if entity not in {"workbook", "organizations", "users"} or format not in {"xlsx", "csv"}:
        raise validation("entity는 workbook|organizations|users, format은 xlsx|csv 이어야 합니다.")
    data, media, name = import_svc.template(entity, format)
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/imports/masters/preview")
def import_preview(request: Request, entity: Annotated[str, Form()], file: Annotated[UploadFile, File()],
                   encoding: Annotated[str, Form()] = "utf-8"):
    rt = rt_of(request)
    data = file.file.read(import_svc.MAX_IMPORT_BYTES + 1)
    name = file.filename or ""
    if rt.maintenance:
        raise ApiError(503, "MAINTENANCE", rt.maintenance_reason)
    with rt.write_factory() as s:  # 검증은 순수 계산, preview 행 저장만 짧은 쓰기
        try:
            out = import_svc.create_preview(s, entity, name, data, encoding)
            s.commit()
        except BaseException:
            s.rollback()
            raise
    return _json(200, {"data": out, "meta": {"requestId": request_id(request)}})


@router.post("/imports/masters/commit")
def import_commit(request: Request, body: sc.ImportCommit):
    return _m(request, body, lambda s, a: import_svc.commit_preview(s, body.preview_token, a), actor_required=False)


# ── 프로젝트 ────────────────────────────────────────────────────────────────

@router.get("/projects")
def list_projects(request: Request, divisionId: str | None = None, teamId: str | None = None, ownerId: str | None = None,
                  memberId: str | None = None, status: str | None = None, q: str | None = None, limit: Limit = 50,
                  cursor: str | None = None):
    return read(request, lambda s: proj_svc.list_projects(s, division_id=divisionId, team_id=teamId, owner_id=ownerId,
                                                          member_id=memberId, status=status, q=q, limit=limit, cursor=cursor))


@router.post("/projects")
def create_project(request: Request, body: sc.ProjectCreate):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: proj_svc.create_project(s, st, body, a), status_code=201)


@router.get("/projects/{project_id}")
def get_project(request: Request, project_id: str):
    return read(request, lambda s: proj_svc.get_project(s, project_id))


@router.patch("/projects/{project_id}")
def patch_project(request: Request, project_id: str, body: sc.ProjectPatch):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: proj_svc.patch_project(s, st, project_id, body, a))


@router.delete("/projects/{project_id}")
def delete_project(request: Request, project_id: str, expectedRevision: int):
    return _m(request, {"expectedRevision": expectedRevision}, lambda s, a: proj_svc.delete_project(s, project_id, expectedRevision, a))


@router.post("/projects/{project_id}/copy")
def copy_project(request: Request, project_id: str, body: sc.ProjectCopy):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: proj_svc.copy_project(s, st, project_id, body, a), status_code=201)


@router.get("/projects/{project_id}/milestones")
def list_milestones(request: Request, project_id: str):
    return read(request, lambda s: proj_svc.list_milestones(s, project_id))


@router.post("/projects/{project_id}/milestones")
def create_milestone(request: Request, project_id: str, body: sc.MilestoneCreate):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: proj_svc.create_milestone(s, st, project_id, body, a), status_code=201)


@router.patch("/milestones/{milestone_id}")
def patch_milestone(request: Request, milestone_id: str, body: sc.MilestonePatch):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: proj_svc.patch_milestone(s, st, milestone_id, body, a))


@router.delete("/milestones/{milestone_id}")
def delete_milestone(request: Request, milestone_id: str, expectedRevision: int):
    return _m(request, {"expectedRevision": expectedRevision}, lambda s, a: proj_svc.delete_milestone(s, milestone_id, expectedRevision, a))


@router.post("/milestones/{milestone_id}/confirm-baseline")
def confirm_baseline(request: Request, milestone_id: str, body: sc.BaselineConfirm):
    return _m(request, body, lambda s, a: proj_svc.confirm_baseline(s, milestone_id, body, a))


@router.get("/projects/{project_id}/kpis")
def list_kpis(request: Request, project_id: str):
    return read(request, lambda s: proj_svc.list_kpis(s, project_id))


@router.post("/projects/{project_id}/kpis")
def create_kpi(request: Request, project_id: str, body: sc.KpiCreate):
    return _m(request, body, lambda s, a: proj_svc.create_kpi(s, project_id, body, a), status_code=201)


@router.patch("/kpis/{kpi_id}")
def patch_kpi(request: Request, kpi_id: str, body: sc.KpiPatch):
    return _m(request, body, lambda s, a: proj_svc.patch_kpi(s, kpi_id, body, a))


# ── 일지 ────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/logs")
def find_logs(request: Request, project_id: str, date: date | None = None, authorId: str | None = None):
    return read(request, lambda s: log_svc.find_logs(s, project_id, date, authorId))


@router.put("/projects/{project_id}/logs/{work_date}/{author_id}")
def put_log(request: Request, project_id: str, work_date: date, author_id: str, body: sc.LogSave):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: log_svc.save_log(s, st, project_id, work_date, author_id, body, a))


@router.get("/logs")
def search_logs(request: Request, dateFrom: date | None = None, dateTo: date | None = None, projectId: str | None = None,
                authorId: str | None = None, teamId: str | None = None, divisionId: str | None = None,
                memberId: str | None = None, status: str | None = None, q: str | None = None, limit: Limit = 200):
    """프로젝트 횡단 일지 조회(업무일지 탭의 날짜별 목록)."""
    return read(request, lambda s: log_svc.search_logs(s, project_id=projectId, author_id=authorId, team_id=teamId,
                                                       division_id=divisionId, member_id=memberId, date_from=dateFrom,
                                                       date_to=dateTo, status=status, name_query=q, limit=limit))


@router.get("/logs/calendar")
def log_calendar(request: Request, dateFrom: date, dateTo: date, projectId: str | None = None, authorId: str | None = None,
                 teamId: str | None = None, divisionId: str | None = None, memberId: str | None = None,
                 status: str | None = None, q: str | None = None):
    return read(request, lambda s: log_svc.log_calendar(s, date_from=dateFrom, date_to=dateTo, project_id=projectId,
                                                        author_id=authorId, team_id=teamId, division_id=divisionId,
                                                        member_id=memberId, status=status, name_query=q))


@router.get("/logs/{log_id}")
def get_log(request: Request, log_id: str):
    return read(request, lambda s: log_svc.get_log(s, log_id))


@router.delete("/logs/{log_id}")
def delete_log(request: Request, log_id: str, expectedRevision: int):
    return _m(request, {"expectedRevision": expectedRevision}, lambda s, a: log_svc.delete_log(s, log_id, expectedRevision, a))


# ── 트래커 ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/todos")
def list_todos(request: Request, project_id: str, status: str | None = None, assigneeId: str | None = None,
               limit: Limit = 100, cursor: str | None = None):
    st = rt_of(request).settings
    return read(request, lambda s: trk_svc.list_todos(s, st, project_id, status, assigneeId, limit, cursor))


@router.post("/projects/{project_id}/todos")
def create_todo(request: Request, project_id: str, body: sc.TodoCreate):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.create_todo(s, st, project_id, body, a), status_code=201)


@router.get("/todos/{todo_id}")
def get_todo(request: Request, todo_id: str):
    st = rt_of(request).settings
    return read(request, lambda s: trk_svc.get_todo(s, st, todo_id))


@router.patch("/todos/{todo_id}")
def patch_todo(request: Request, todo_id: str, body: sc.TodoPatch):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.patch_todo(s, st, todo_id, body, a))


@router.delete("/todos/{todo_id}")
def delete_todo(request: Request, todo_id: str, expectedRevision: int):
    return _m(request, {"expectedRevision": expectedRevision}, lambda s, a: trk_svc.delete_tracker(s, "todo", todo_id, expectedRevision, a))


@router.post("/todos/{todo_id}/complete")
def complete_todo(request: Request, todo_id: str, body: sc.CompleteBody):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.complete_todo(s, st, todo_id, body, a))


@router.post("/todos/{todo_id}/reopen")
def reopen_todo(request: Request, todo_id: str, body: sc.SimpleTransition):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.reopen_todo(s, st, todo_id, body, a))


@router.get("/projects/{project_id}/issues")
def list_issues(request: Request, project_id: str, status: str | None = None, assigneeId: str | None = None,
                limit: Limit = 100, cursor: str | None = None):
    st = rt_of(request).settings
    return read(request, lambda s: trk_svc.list_issues(s, st, project_id, status, assigneeId, limit, cursor))


@router.post("/projects/{project_id}/issues")
def create_issue(request: Request, project_id: str, body: sc.IssueCreate):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.create_issue(s, st, project_id, body, a), status_code=201)


@router.get("/issues/{issue_id}")
def get_issue(request: Request, issue_id: str):
    st = rt_of(request).settings
    return read(request, lambda s: trk_svc.get_issue(s, st, issue_id))


@router.patch("/issues/{issue_id}")
def patch_issue(request: Request, issue_id: str, body: sc.IssuePatch):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.patch_issue(s, st, issue_id, body, a))


@router.delete("/issues/{issue_id}")
def delete_issue(request: Request, issue_id: str, expectedRevision: int):
    return _m(request, {"expectedRevision": expectedRevision}, lambda s, a: trk_svc.delete_tracker(s, "issue", issue_id, expectedRevision, a))


@router.post("/issues/{issue_id}/todos")
def issue_todo(request: Request, issue_id: str, body: sc.IssueTodoCreate):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.create_response_todo(s, st, issue_id, body, a), status_code=201)


@router.post("/issues/{issue_id}/resolve")
def resolve_issue(request: Request, issue_id: str, body: sc.CompleteBody):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.resolve_issue(s, st, issue_id, body, a))


@router.post("/issues/{issue_id}/close")
def close_issue(request: Request, issue_id: str, body: sc.SimpleTransition):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.close_issue(s, st, issue_id, body, a))


@router.post("/issues/{issue_id}/reopen")
def reopen_issue(request: Request, issue_id: str, body: sc.SimpleTransition):
    st = rt_of(request).settings
    return _m(request, body, lambda s, a: trk_svc.reopen_issue(s, st, issue_id, body, a))


# ── 첨부 ────────────────────────────────────────────────────────────────────

@router.post("/attachments")
def upload_attachment(request: Request, projectId: Annotated[str, Form()], file: Annotated[UploadFile, File()]):
    rt = rt_of(request)
    if rt.maintenance:
        raise ApiError(503, "MAINTENANCE", rt.maintenance_reason)
    actor = request.headers.get("X-Actor-Id")
    with rt.read_factory() as s:  # 사전 확인만 짧게. 파일 처리는 트랜잭션 밖.
        load_actor(s, actor)
        proj_svc.require_active_project(s, projectId)
    new = new_id()
    stored = att_svc.store_upload(rt.settings, projectId, file.filename or "file", file.file, new)
    try:
        with rt.write_factory() as ws:
            att = att_svc.register(ws, stored, actor)  # type: ignore[arg-type]
            ws.commit()
            out = att_svc.ser_attachment(att)
    except BaseException:
        att_svc.attachment_abs_path(rt.settings, stored.relative_path).unlink(missing_ok=True)
        raise
    return _json(201, {"data": out, "meta": {"requestId": request_id(request)}})


def _file_response(rt, a: Attachment) -> FileResponse:
    path = att_svc.attachment_abs_path(rt.settings, a.stored_relative_path)
    if not path.exists():
        raise not_found("첨부 파일", a.id)
    inline = a.media_type in IMAGE_MEDIA_TYPES
    return FileResponse(path, media_type=a.media_type, filename=a.original_name,
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


@router.get("/attachments/{attachment_id}/content")
def attachment_content(request: Request, attachment_id: str):
    rt = rt_of(request)
    with rt.read_factory() as s:
        a = att_svc.get_attachment(s, attachment_id)
        s.expunge(a)
    return _file_response(rt, a)


@router.get("/attachment-uses/{use_id}/content")
def attachment_use_content(request: Request, use_id: str):
    rt = rt_of(request)
    with rt.read_factory() as s:
        a = att_svc.resolve_use(s, use_id)
        s.expunge(a)
    return _file_response(rt, a)


# ── 휴지통 ──────────────────────────────────────────────────────────────────

@router.get("/trash")
def trash(request: Request):
    return read(request, trash_svc.list_trash)


@router.post("/trash/{entity_type}/{entity_id}/restore")
def restore(request: Request, entity_type: str, entity_id: str):
    return _m(request, {"t": entity_type, "id": entity_id}, lambda s, a: trash_svc.restore(s, entity_type, entity_id, a))


# ── 내보내기 / 백업 ─────────────────────────────────────────────────────────

@router.get("/exports/status")
def exports_status(request: Request, projectId: str | None = None):
    st = rt_of(request).settings
    return read(request, lambda s: export_svc.export_status(s, st, projectId))


@router.post("/exports/rebuild")
def exports_rebuild(request: Request, body: sc.RebuildBody):
    return _m(request, body, lambda s, a: {"requestedTargets": export_svc.request_rebuild(s, body.project_id, body.all)}, status_code=202)


@router.post("/exports/bundle")
def exports_bundle(request: Request, body: sc.BundleBody):
    rt = rt_of(request)
    with rt.read_factory() as s:
        load_actor(s, request.headers.get("X-Actor-Id"))
    out = export_svc.build_bundle(rt.read_factory, rt.settings, body.project_id, body.date_from, body.date_to, body.include_attachments)
    if "error" in out:
        raise ApiError(409, out["error"], "삭제되었거나 없는 프로젝트는 bundle로 만들 수 없습니다.")
    return _json(200, {"data": out, "meta": {"requestId": request_id(request)}})


@router.get("/backups")
def backups(request: Request):
    return read(request, backup_svc.list_backups)


@router.post("/backups")
def backup_now(request: Request):
    rt = rt_of(request)
    code, resp = mutate(request, {"op": "backup-now"}, lambda s, a: backup_svc.ser_backup(backup_svc.request_manual_backup(s)),
                        status_code=202)
    run_id = resp["data"]["id"]
    # 즉시 실행(작업 스레드와 중복되지 않도록 backup_lock 으로 직렬화)
    backup_svc.run_backup(rt, run_id)
    with rt.read_factory() as s:
        resp["data"] = backup_svc.ser_backup(s.get(BackupRun, run_id))
    return _json(code, resp)


@router.post("/backups/{backup_id}/restore")
def backup_restore(request: Request, backup_id: str, body: sc.RestoreBody):
    rt = rt_of(request)
    with rt.read_factory() as s:
        actor = load_actor(s, request.headers.get("X-Actor-Id")).id
    out = backup_svc.restore_backup(rt, backup_id, actor)
    return _json(200, {"data": out, "meta": {"requestId": request_id(request)}})

