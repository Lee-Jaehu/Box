"""프로젝트 / 마일스톤 / KPI. 프로젝트 생성 시 '일반·수시 업무' 마일스톤을 자동 생성한다."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..documents import require_valid
from ..errors import ApiError, conflict, validation
from ..models import DailyLog, Milestone, Organization, Project, ProjectKpi, ProjectMember, User, utcnow
from ..schemas import (BaselineConfirm, KpiCreate, KpiPatch, MilestoneCreate, MilestonePatch, ProjectCopy,
                       ProjectCreate, ProjectPatch)
from .common import audit, bump, check_revision, get_or_404, iso, iso_date, mark_export, stamp_new
from .masters import paginate

GENERAL_NAME = "일반·수시 업무"


def check_range(start: date | None, end: date | None, field_start: str, field_end: str) -> None:
    if start and end and end < start:
        raise validation("종료일은 시작일보다 빠를 수 없습니다.",
                         [{"field": field_end, "code": "END_BEFORE_START", "message": "종료일이 시작일보다 빠릅니다."}])


def require_active_project(s: Session, project_id: str, *, for_write: bool = True) -> Project:
    p = s.get(Project, project_id)
    if p is None:
        raise ApiError(404, "NOT_FOUND", "프로젝트를 찾을 수 없습니다.", resource_id=project_id)
    if p.deleted_at is not None:
        raise conflict("PROJECT_IN_TRASH", "휴지통에 있는 프로젝트입니다. 복원한 뒤 이어서 작업해 주세요.", resource_id=p.id)
    return p


def ser_milestone(m: Milestone) -> dict:
    return {
        "id": m.id, "projectId": m.project_id, "name": m.name, "descriptionDoc": m.description_doc,
        "isGeneral": m.is_general, "sortOrder": m.sort_order, "status": m.status,
        "plannedStart": iso_date(m.planned_start), "plannedEnd": iso_date(m.planned_end),
        "baselineStart": iso_date(m.baseline_start), "baselineEnd": iso_date(m.baseline_end),
        "actualStart": iso_date(m.actual_start), "actualEnd": iso_date(m.actual_end),
        "baselineConfirmedAt": iso(m.baseline_confirmed_at), "revision": m.revision, "deletedAt": iso(m.deleted_at),
    }


def ser_kpi(k: ProjectKpi) -> dict:
    return {"id": k.id, "projectId": k.project_id, "name": k.name, "unit": k.unit, "baselineValue": k.baseline_value,
            "targetValue": k.target_value, "direction": k.direction, "active": k.active, "revision": k.revision,
            "deletedAt": iso(k.deleted_at)}


def _members(s: Session, project_id: str) -> list[str]:
    return [r for r in s.execute(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)).scalars()]


def milestone_summaries(s: Session, project_ids: list[str]) -> dict[str, dict]:
    """과제별 마일스톤 집계 {total, completed, cancelled} (일반·수시 업무와 삭제된 마일스톤 제외). 쿼리 1번."""
    out = {pid: {"total": 0, "completed": 0, "cancelled": 0} for pid in project_ids}
    if not project_ids:
        return out
    rows = s.execute(select(Milestone.project_id, Milestone.status, func.count())
                     .where(Milestone.project_id.in_(project_ids), Milestone.deleted_at.is_(None), Milestone.is_general.is_(False))
                     .group_by(Milestone.project_id, Milestone.status))
    for pid, status, n in rows:
        out[pid]["total"] += n
        if status in ("completed", "cancelled"):
            out[pid][status] += n
    return out


def project_people(s: Session, projects: list[Project]) -> dict[str, list[dict]]:
    """과제별 사람 목록 (왼쪽 트리 PJT ▸ User ▸ Worklog): 대표 → 참여자(이름순) → 참여자가 아니지만 일지를 쓴 사람(이름순).

    일지 작성자는 삭제되지 않은 일지 기준. 페이지 단위로 참여자 1번·작성자 1번·이름 1번 조회.
    """
    ids = [p.id for p in projects]
    if not ids:
        return {}
    members: dict[str, list[str]] = {pid: [] for pid in ids}
    for pid, uid in s.execute(select(ProjectMember.project_id, ProjectMember.user_id).where(ProjectMember.project_id.in_(ids))):
        members[pid].append(uid)
    authors: dict[str, list[str]] = {pid: [] for pid in ids}
    for pid, uid in s.execute(select(DailyLog.project_id, DailyLog.author_id).where(DailyLog.project_id.in_(ids), DailyLog.deleted_at.is_(None)).distinct()):
        authors[pid].append(uid)
    every = {p.owner_user_id for p in projects} | {u for v in members.values() for u in v} | {u for v in authors.values() for u in v}
    names = dict(s.execute(select(User.id, User.name).where(User.id.in_(every))).all()) if every else {}
    out = {}
    for p in projects:
        by_name = lambda uid: (names.get(uid) or "", uid)  # noqa: E731
        member_ids = sorted({u for u in members[p.id] if u != p.owner_user_id}, key=by_name)
        author_ids = sorted({u for u in authors[p.id] if u != p.owner_user_id and u not in member_ids}, key=by_name)
        out[p.id] = ([{"id": p.owner_user_id, "name": names.get(p.owner_user_id), "role": "owner"}]
                     + [{"id": u, "name": names.get(u), "role": "member"} for u in member_ids]
                     + [{"id": u, "name": names.get(u), "role": "author"} for u in author_ids])
    return out


def ser_project(s: Session, p: Project, *, detail: bool = False, summary: dict | None = None,
                people: list[dict] | None = None) -> dict:
    team = s.get(Organization, p.team_id)
    division = s.get(Organization, team.parent_id) if team and team.parent_id else None
    owner = s.get(User, p.owner_user_id)
    d = {
        "id": p.id, "name": p.name, "teamId": p.team_id, "teamName": team.name if team else None,
        "divisionId": division.id if division else None, "divisionName": division.name if division else None,
        "ownerUserId": p.owner_user_id, "ownerName": owner.name if owner else None,
        "isShortTerm": p.is_short_term, "status": p.status, "startDate": iso_date(p.start_date),
        "endDate": iso_date(p.end_date), "revision": p.revision, "deletedAt": iso(p.deleted_at),
        "memberIds": _members(s, p.id),
        # 내비게이션 트리의 완료(검회색) 판정용: 일반·수시 업무를 뺀 마일스톤 상태 집계
        "milestoneSummary": summary if summary is not None else milestone_summaries(s, [p.id])[p.id],
        # 왼쪽 트리 PJT ▸ User: 대표·참여자·일지 작성자
        "people": people if people is not None else project_people(s, [p])[p.id],
    }
    if detail:
        d.update(backgroundDoc=p.background_doc, purposeDoc=p.purpose_doc, retrospectiveDoc=p.retrospective_doc)
        ms = s.execute(select(Milestone).where(Milestone.project_id == p.id, Milestone.deleted_at.is_(None))
                       .order_by(Milestone.is_general.desc(), Milestone.sort_order, Milestone.created_at)).scalars().all()
        d["milestones"] = [ser_milestone(m) for m in ms]
        ks = s.execute(select(ProjectKpi).where(ProjectKpi.project_id == p.id, ProjectKpi.deleted_at.is_(None))
                       .order_by(ProjectKpi.created_at)).scalars().all()
        d["kpis"] = [ser_kpi(k) for k in ks]
        # 단발성 토글에서 숨겨진 상세가 '입력됨'인지 알려준다(값은 삭제하지 않는다).
        d["hasDetail"] = {
            "background": bool(p.background_doc), "purpose": bool(p.purpose_doc),
            "kpis": bool(ks), "milestones": any(not m.is_general for m in ms),
        }
    return d


# ── 프로젝트 ────────────────────────────────────────────────────────────────

def _check_people(s: Session, team_id: str, owner_id: str, member_ids: list[str]) -> list[str]:
    team = s.get(Organization, team_id)
    if team is None or team.deleted_at is not None or team.kind != "team":
        raise validation("담당 팀을 찾을 수 없습니다.", [{"field": "teamId", "code": "NOT_FOUND", "message": "팀을 선택해 주세요."}])
    ids = list(dict.fromkeys([owner_id, *member_ids]))  # 대표도 멤버에 포함, 순서 유지
    users = {u.id: u for u in s.execute(select(User).where(User.id.in_(ids))).scalars()}
    for uid in ids:
        u = users.get(uid)
        if u is None or u.deleted_at is not None:
            raise validation("담당자를 찾을 수 없습니다.", [{"field": "ownerUserId" if uid == owner_id else "memberIds", "code": "NOT_FOUND", "message": uid}])
    return ids


def create_project(s: Session, settings: Settings, body: ProjectCreate, actor_id: str) -> dict:
    check_range(body.start_date, body.end_date, "startDate", "endDate")
    ids = _check_people(s, body.team_id, body.owner_user_id, body.member_ids)
    for fld, doc in (("backgroundDoc", body.background_doc), ("purposeDoc", body.purpose_doc)):
        if doc is not None:
            require_valid(doc, settings, fld)
    p = Project(name=body.name.strip(), team_id=body.team_id, owner_user_id=body.owner_user_id,
                is_short_term=body.is_short_term, status=body.status, start_date=body.start_date,
                end_date=body.end_date, background_doc=body.background_doc, purpose_doc=body.purpose_doc)
    stamp_new(p, actor_id)
    s.add(p)
    s.flush()
    for uid in ids:
        s.add(ProjectMember(project_id=p.id, user_id=uid))
    g = Milestone(project_id=p.id, name=GENERAL_NAME, is_general=True, sort_order=0, status="planned")
    stamp_new(g, actor_id)
    s.add(g)
    s.flush()
    audit(s, "project.create", "project", p.id, actor_id, {"name": p.name})
    mark_export(s, "project", p.id)
    mark_export(s, "trackers", p.id)
    return ser_project(s, p, detail=True)


def list_projects(s: Session, *, division_id: str | None, team_id: str | None, owner_id: str | None,
                  member_id: str | None, status: str | None, q: str | None, limit: int, cursor: str | None) -> dict:
    stmt = select(Project).where(Project.deleted_at.is_(None)).order_by(Project.updated_at.desc(), Project.id)
    if team_id:
        stmt = stmt.where(Project.team_id == team_id)
    if division_id:
        stmt = stmt.where(Project.team_id.in_(select(Organization.id).where(Organization.parent_id == division_id)))
    if owner_id:
        stmt = stmt.where(Project.owner_user_id == owner_id)
    if member_id:
        stmt = stmt.where(Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == member_id)))
    if status:
        stmt = stmt.where(Project.status == status)
    if q:
        stmt = stmt.where(Project.name.like(f"%{q.strip()}%"))
    rows, nxt = paginate(s, stmt, limit, cursor)
    summaries = milestone_summaries(s, [p.id for p in rows])
    people = project_people(s, rows)
    return {"items": [ser_project(s, p, summary=summaries[p.id], people=people[p.id]) for p in rows], "nextCursor": nxt}


def get_project(s: Session, project_id: str) -> dict:
    return ser_project(s, get_or_404(s, Project, project_id, "프로젝트"), detail=True)


def patch_project(s: Session, settings: Settings, project_id: str, body: ProjectPatch, actor_id: str) -> dict:
    p = require_active_project(s, project_id)
    check_revision(p, body.expected_revision, "프로젝트")
    if body.name is not None:
        p.name = body.name.strip()
    if body.is_short_term is not None:
        p.is_short_term = body.is_short_term
    if body.status is not None:
        p.status = body.status
    if body.clear_dates:
        p.start_date = p.end_date = None
    else:
        if "start_date" in body.model_fields_set:
            p.start_date = body.start_date
        if "end_date" in body.model_fields_set:
            p.end_date = body.end_date
    check_range(p.start_date, p.end_date, "startDate", "endDate")
    for attr, field in (("background_doc", "backgroundDoc"), ("purpose_doc", "purposeDoc"), ("retrospective_doc", "retrospectiveDoc")):
        if attr in body.model_fields_set:
            doc = getattr(body, attr)
            if doc is not None:
                require_valid(doc, settings, field)
            setattr(p, attr, doc)
    if body.team_id is not None or body.owner_user_id is not None or body.member_ids is not None:
        team_id = body.team_id or p.team_id
        owner = body.owner_user_id or p.owner_user_id
        members = body.member_ids if body.member_ids is not None else _members(s, p.id)
        ids = _check_people(s, team_id, owner, members)
        p.team_id, p.owner_user_id = team_id, owner
        s.query(ProjectMember).filter(ProjectMember.project_id == p.id).delete()
        for uid in ids:
            s.add(ProjectMember(project_id=p.id, user_id=uid))
    bump(p, actor_id)
    s.flush()
    audit(s, "project.update", "project", p.id, actor_id, {"fields": sorted(body.model_fields_set - {"expected_revision"})})
    mark_export(s, "project", p.id)
    return ser_project(s, p, detail=True)


def copy_project(s: Session, settings: Settings, project_id: str, body: ProjectCopy, actor_id: str) -> dict:
    """기본정보 재사용. 일지/트래커/실적/이력/첨부/기간은 복사하지 않고 ID는 모두 새로 발급한다."""
    src = get_or_404(s, Project, project_id, "프로젝트")
    new = Project(name=body.name.strip(), team_id=src.team_id, owner_user_id=src.owner_user_id,
                  is_short_term=src.is_short_term, status="preparing",
                  background_doc=src.background_doc, purpose_doc=src.purpose_doc)
    stamp_new(new, actor_id)
    s.add(new)
    s.flush()
    for uid in _members(s, src.id):
        s.add(ProjectMember(project_id=new.id, user_id=uid))
    g = Milestone(project_id=new.id, name=GENERAL_NAME, is_general=True, sort_order=0, status="planned")
    stamp_new(g, actor_id)
    s.add(g)
    if body.copy_milestones:
        for m in s.execute(select(Milestone).where(Milestone.project_id == src.id, Milestone.deleted_at.is_(None),
                                                   Milestone.is_general.is_(False)).order_by(Milestone.sort_order)).scalars():
            nm = Milestone(project_id=new.id, name=m.name, description_doc=m.description_doc, sort_order=m.sort_order)
            stamp_new(nm, actor_id)
            s.add(nm)
    if body.copy_kpis:
        for k in s.execute(select(ProjectKpi).where(ProjectKpi.project_id == src.id, ProjectKpi.deleted_at.is_(None))).scalars():
            nk = ProjectKpi(project_id=new.id, name=k.name, unit=k.unit, baseline_value=k.baseline_value,
                            target_value=k.target_value, direction=k.direction, active=k.active)
            stamp_new(nk, actor_id)
            s.add(nk)
    s.flush()
    audit(s, "project.copy", "project", new.id, actor_id, {"sourceProjectId": src.id})
    mark_export(s, "project", new.id)
    mark_export(s, "trackers", new.id)
    return ser_project(s, new, detail=True)


def delete_project(s: Session, project_id: str, expected_revision: int, actor_id: str) -> dict:
    p = get_or_404(s, Project, project_id, "프로젝트")
    check_revision(p, expected_revision, "프로젝트")
    p.deleted_at = utcnow()
    bump(p, actor_id)
    audit(s, "project.delete", "project", p.id, actor_id)
    mark_export(s, "project", p.id)  # project.json tombstone(deletedAt)
    return {"id": p.id, "deletedAt": iso(p.deleted_at), "revision": p.revision}


# ── 마일스톤 ────────────────────────────────────────────────────────────────

def list_milestones(s: Session, project_id: str) -> dict:
    get_or_404(s, Project, project_id, "프로젝트")
    ms = s.execute(select(Milestone).where(Milestone.project_id == project_id, Milestone.deleted_at.is_(None))
                   .order_by(Milestone.is_general.desc(), Milestone.sort_order, Milestone.created_at)).scalars().all()
    return {"items": [ser_milestone(m) for m in ms]}


def _similar(s: Session, project_id: str, name: str) -> list[str]:
    """유사 이름 안내용(자동 병합 없음)."""
    key = "".join(name.split()).lower()
    out = []
    for m in s.execute(select(Milestone).where(Milestone.project_id == project_id, Milestone.deleted_at.is_(None))).scalars():
        other = "".join(m.name.split()).lower()
        if other == key or (len(key) >= 2 and (key in other or other in key)):
            out.append(m.name)
    return out


def create_milestone(s: Session, settings: Settings, project_id: str, body: MilestoneCreate, actor_id: str) -> dict:
    p = require_active_project(s, project_id)
    check_range(body.planned_start, body.planned_end, "plannedStart", "plannedEnd")
    if body.description_doc is not None:
        require_valid(body.description_doc, settings, "descriptionDoc")
    similar = _similar(s, project_id, body.name)
    nxt = (s.execute(select(Milestone.sort_order).where(Milestone.project_id == project_id)
                     .order_by(Milestone.sort_order.desc()).limit(1)).scalar() or 0) + 1
    m = Milestone(project_id=p.id, name=body.name.strip(), description_doc=body.description_doc, sort_order=nxt,
                  planned_start=body.planned_start, planned_end=body.planned_end)
    stamp_new(m, actor_id)
    s.add(m)
    s.flush()
    audit(s, "milestone.create", "milestone", m.id, actor_id, {"name": m.name})
    mark_export(s, "project", p.id)
    out = ser_milestone(m)
    out["similarNames"] = similar
    return out


def patch_milestone(s: Session, settings: Settings, milestone_id: str, body: MilestonePatch, actor_id: str) -> dict:
    m = get_or_404(s, Milestone, milestone_id, "마일스톤")
    require_active_project(s, m.project_id)
    check_revision(m, body.expected_revision, "마일스톤")
    sched = {"planned_start", "planned_end", "actual_start", "actual_end", "clear_planned"} & body.model_fields_set
    if m.is_general and sched:
        raise validation("일반·수시 업무는 일정을 가질 수 없습니다.", [{"field": "plannedStart", "code": "GENERAL_NO_SCHEDULE", "message": "일정 없음"}])
    if body.name is not None:
        m.name = body.name.strip()
    if "description_doc" in body.model_fields_set:
        if body.description_doc is not None:
            require_valid(body.description_doc, settings, "descriptionDoc")
        m.description_doc = body.description_doc
    if body.status is not None:
        m.status = body.status
    if body.sort_order is not None:
        m.sort_order = body.sort_order
    # 공용 간트의 막대 이동/크기 변경은 '현재 계획'만 수정한다. 확정 기준·실제일은 자동 변경하지 않는다.
    if body.clear_planned:
        m.planned_start = m.planned_end = None
    else:
        if "planned_start" in body.model_fields_set:
            m.planned_start = body.planned_start
        if "planned_end" in body.model_fields_set:
            m.planned_end = body.planned_end
    if "actual_start" in body.model_fields_set:
        m.actual_start = body.actual_start
    if "actual_end" in body.model_fields_set:
        m.actual_end = body.actual_end
    check_range(m.planned_start, m.planned_end, "plannedStart", "plannedEnd")
    check_range(m.actual_start, m.actual_end, "actualStart", "actualEnd")
    bump(m, actor_id)
    s.flush()
    audit(s, "milestone.update", "milestone", m.id, actor_id, {"fields": sorted(body.model_fields_set - {"expected_revision"})})
    mark_export(s, "project", m.project_id)
    return ser_milestone(m)


def confirm_baseline(s: Session, milestone_id: str, body: BaselineConfirm, actor_id: str) -> dict:
    m = get_or_404(s, Milestone, milestone_id, "마일스톤")
    require_active_project(s, m.project_id)
    check_revision(m, body.expected_revision, "마일스톤")
    if m.is_general or not (m.planned_start and m.planned_end):
        raise validation("계획 시작/종료일이 있어야 기준 일정을 확정할 수 있습니다.",
                         [{"field": "plannedStart", "code": "PLAN_REQUIRED", "message": "계획 일정을 먼저 입력해 주세요."}])
    before = {"baselineStart": iso_date(m.baseline_start), "baselineEnd": iso_date(m.baseline_end)}
    m.baseline_start, m.baseline_end = m.planned_start, m.planned_end
    m.baseline_confirmed_at = utcnow()
    bump(m, actor_id)
    s.flush()
    audit(s, "milestone.baseline_confirm", "milestone", m.id, actor_id,
          {"before": before, "after": {"baselineStart": iso_date(m.baseline_start), "baselineEnd": iso_date(m.baseline_end)}})
    mark_export(s, "project", m.project_id)
    return ser_milestone(m)


def delete_milestone(s: Session, milestone_id: str, expected_revision: int, actor_id: str) -> dict:
    m = get_or_404(s, Milestone, milestone_id, "마일스톤")
    require_active_project(s, m.project_id)
    check_revision(m, expected_revision, "마일스톤")
    if m.is_general:
        raise conflict("GENERAL_MILESTONE_PROTECTED", "일반·수시 업무는 삭제할 수 없습니다.")
    m.deleted_at = utcnow()  # 기존 일지 TASK 는 snapshot 으로 보존되고, 새 선택에서만 제외된다.
    bump(m, actor_id)
    audit(s, "milestone.delete", "milestone", m.id, actor_id)
    mark_export(s, "project", m.project_id)
    return {"id": m.id, "deletedAt": iso(m.deleted_at), "revision": m.revision}


# ── KPI ─────────────────────────────────────────────────────────────────────

def _dec_or_none(v: str | None, field: str) -> str | None:
    if v is None or not str(v).strip():
        return None
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        raise validation("숫자 형식이 올바르지 않습니다.", [{"field": field, "code": "NOT_A_NUMBER", "message": "숫자"}]) from None
    if not d.is_finite():
        raise validation("숫자 형식이 올바르지 않습니다.", [{"field": field, "code": "NOT_A_NUMBER", "message": "숫자"}])
    return format(d.normalize(), "f")


def list_kpis(s: Session, project_id: str) -> dict:
    get_or_404(s, Project, project_id, "프로젝트")
    ks = s.execute(select(ProjectKpi).where(ProjectKpi.project_id == project_id, ProjectKpi.deleted_at.is_(None))
                   .order_by(ProjectKpi.created_at)).scalars().all()
    return {"items": [ser_kpi(k) for k in ks]}


def create_kpi(s: Session, project_id: str, body: KpiCreate, actor_id: str) -> dict:
    p = require_active_project(s, project_id)
    k = ProjectKpi(project_id=p.id, name=body.name.strip(), unit=body.unit, direction=body.direction,
                   baseline_value=_dec_or_none(body.baseline_value, "baselineValue"),
                   target_value=_dec_or_none(body.target_value, "targetValue"))
    stamp_new(k, actor_id)
    s.add(k)
    s.flush()
    audit(s, "kpi.create", "kpi", k.id, actor_id, {"name": k.name})
    mark_export(s, "project", p.id)
    return ser_kpi(k)


def patch_kpi(s: Session, kpi_id: str, body: KpiPatch, actor_id: str) -> dict:
    k = get_or_404(s, ProjectKpi, kpi_id, "KPI")
    require_active_project(s, k.project_id)
    check_revision(k, body.expected_revision, "KPI")
    if body.name is not None:
        k.name = body.name.strip()
    for attr, field in (("unit", "unit"), ("direction", "direction")):
        if attr in body.model_fields_set:
            setattr(k, attr, getattr(body, attr))
    if "baseline_value" in body.model_fields_set:
        k.baseline_value = _dec_or_none(body.baseline_value, "baselineValue")
    if "target_value" in body.model_fields_set:
        k.target_value = _dec_or_none(body.target_value, "targetValue")
    if body.active is not None:
        k.active = body.active
    bump(k, actor_id)
    s.flush()
    audit(s, "kpi.update", "kpi", k.id, actor_id)
    mark_export(s, "project", k.project_id)
    return ser_kpi(k)
