"""휴지통. 프로젝트 삭제는 하위를 개별 삭제하지 않고 상위에서 접근을 막는다. 자동 영구 삭제 없음."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError, conflict, validation
from ..models import DailyLog, Issue, Milestone, Project, Todo
from .common import audit, bump, get_or_404, iso, iso_date, mark_export

MODELS = {"project": Project, "milestone": Milestone, "log": DailyLog, "todo": Todo, "issue": Issue}


def _project_active(s: Session, project_id: str) -> bool:
    p = s.get(Project, project_id)
    return p is not None and p.deleted_at is None


def list_trash(s: Session) -> dict:
    items: list[dict] = []
    for p in s.execute(select(Project).where(Project.deleted_at.is_not(None))).scalars():
        items.append({"entityType": "project", "id": p.id, "title": p.name, "projectId": p.id, "deletedAt": iso(p.deleted_at)})
    # 삭제된 프로젝트 아래의 항목은 프로젝트와 함께 숨겨진다(복원 시 원래 상태로 돌아옴).
    for m in s.execute(select(Milestone).where(Milestone.deleted_at.is_not(None))).scalars():
        if _project_active(s, m.project_id):
            items.append({"entityType": "milestone", "id": m.id, "title": m.name, "projectId": m.project_id, "deletedAt": iso(m.deleted_at)})
    for lg in s.execute(select(DailyLog).where(DailyLog.deleted_at.is_not(None))).scalars():
        if _project_active(s, lg.project_id):
            items.append({"entityType": "log", "id": lg.id, "title": f"{iso_date(lg.work_date)} 일지", "projectId": lg.project_id,
                          "deletedAt": iso(lg.deleted_at), "workDate": iso_date(lg.work_date), "authorId": lg.author_id})
    for kind, model in (("todo", Todo), ("issue", Issue)):
        for t in s.execute(select(model).where(model.deleted_at.is_not(None))).scalars():
            if _project_active(s, t.project_id):
                items.append({"entityType": kind, "id": t.id, "title": kind.upper(), "projectId": t.project_id, "deletedAt": iso(t.deleted_at)})
    items.sort(key=lambda x: x["deletedAt"] or "", reverse=True)
    return {"items": items}


def restore(s: Session, entity_type: str, entity_id: str, actor_id: str) -> dict:
    model = MODELS.get(entity_type)
    if model is None:
        raise ApiError(404, "NOT_FOUND", "알 수 없는 항목 종류입니다.")
    obj = get_or_404(s, model, entity_id, "항목", include_deleted=True)
    if obj.deleted_at is None:
        raise conflict("NOT_DELETED", "삭제된 항목이 아닙니다.", current_revision=obj.revision)
    if entity_type != "project" and not _project_active(s, obj.project_id):
        raise conflict("PROJECT_IN_TRASH", "상위 프로젝트가 휴지통에 있습니다. 프로젝트를 먼저 복원해 주세요.", resource_id=obj.project_id)
    if entity_type == "log":
        clash = s.execute(select(DailyLog.id).where(DailyLog.project_id == obj.project_id, DailyLog.author_id == obj.author_id,
                                                    DailyLog.work_date == obj.work_date, DailyLog.id != obj.id,
                                                    DailyLog.deleted_at.is_(None))).first()
        if clash:  # unique 제약상 불가능하지만 방어적으로 확인
            raise validation("같은 날짜의 활성 일지가 이미 있습니다.")
    obj.deleted_at = None
    bump(obj, actor_id)
    s.flush()
    audit(s, f"{entity_type}.restore", entity_type, obj.id, actor_id)
    if entity_type == "project":
        mark_export(s, "project", obj.id)
        mark_export(s, "trackers", obj.id)
    elif entity_type == "log":
        mark_export(s, "daily", obj.project_id, obj.work_date)
    elif entity_type == "milestone":
        mark_export(s, "project", obj.project_id)
    else:
        mark_export(s, "trackers", obj.project_id)
    return {"entityType": entity_type, "id": obj.id, "revision": obj.revision}
