"""조직/사용자 기준정보. 사번은 선택(nullable), 식별은 내부 UUID. 참조 중 물리 삭제 없이 비활성화만."""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..errors import conflict, validation
from ..models import Organization, User
from ..schemas import OrgCreate, OrgPatch, UserCreate, UserPatch
from .common import audit, bump, check_revision, get_or_404, iso, mark_export, stamp_new


def paginate(s: Session, stmt, limit: int, cursor: str | None) -> tuple[list[Any], str | None]:
    limit = max(1, min(limit, 200))
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    rows = s.execute(stmt.limit(limit + 1).offset(offset)).scalars().all()
    nxt = str(offset + limit) if len(rows) > limit else None
    return rows[:limit], nxt


def ser_org(o: Organization) -> dict:
    return {"id": o.id, "name": o.name, "kind": o.kind, "parentId": o.parent_id, "externalKey": o.external_key,
            "active": o.active, "revision": o.revision, "deletedAt": iso(o.deleted_at)}


def ser_user(u: User, team: Organization | None = None, division: Organization | None = None) -> dict:
    d = {"id": u.id, "name": u.name, "teamId": u.team_id, "employeeNumber": u.employee_number,
         "externalKey": u.external_key, "active": u.active, "revision": u.revision, "deletedAt": iso(u.deleted_at)}
    if team is not None:
        d["teamName"] = team.name
        d["divisionId"] = division.id if division else None
        d["divisionName"] = division.name if division else None
    return d


def norm_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None  # "0" 은 유효한 값, 빈 문자열만 null


def master_revision(s: Session) -> str:
    """조직/사용자 현재 상태 지문. import preview 이후 명단이 바뀌었는지 판단한다."""
    h = hashlib.sha256()
    for model in (Organization, User):
        for id_, rev, deleted in s.execute(select(model.id, model.revision, model.deleted_at).order_by(model.id)):
            h.update(f"{id_}:{rev}:{int(deleted is not None)}|".encode())
    return h.hexdigest()


# ── 조직 ────────────────────────────────────────────────────────────────────

def _validate_parent(s: Session, kind: str, parent_id: str | None, self_id: str | None = None) -> None:
    if parent_id is None:
        return
    parent = s.get(Organization, parent_id)
    if parent is None or parent.deleted_at is not None:
        raise validation("상위 조직을 찾을 수 없습니다.", [{"field": "parentId", "code": "NOT_FOUND", "message": "상위 조직 없음"}])
    if kind == "division":
        raise validation("상위 조직이 없는 담당 조직(division)입니다.", [{"field": "parentId", "code": "INVALID", "message": "division은 상위 조직을 가질 수 없습니다."}])
    if parent.kind != "division":
        raise validation("팀의 상위는 담당 조직이어야 합니다.", [{"field": "parentId", "code": "INVALID", "message": "team의 parent는 division"}])
    if self_id and parent_id == self_id:
        raise validation("자기 자신을 상위로 지정할 수 없습니다.")


def _check_org_key(s: Session, key: str | None, self_id: str | None) -> None:
    if key is None:
        return
    q = select(Organization.id).where(Organization.external_key == key)
    if self_id:
        q = q.where(Organization.id != self_id)
    if s.execute(q).first():
        raise conflict("DUPLICATE_EXTERNAL_KEY", "이미 사용 중인 조직 코드입니다.")


def list_orgs(s: Session, kind: str | None, include_inactive: bool, limit: int, cursor: str | None) -> dict:
    stmt = select(Organization).where(Organization.deleted_at.is_(None)).order_by(Organization.kind, Organization.name, Organization.id)
    if kind:
        stmt = stmt.where(Organization.kind == kind)
    if not include_inactive:
        stmt = stmt.where(Organization.active.is_(True))
    rows, nxt = paginate(s, stmt, limit, cursor)
    return {"items": [ser_org(o) for o in rows], "nextCursor": nxt}


def create_org(s: Session, body: OrgCreate, actor_id: str) -> dict:
    key = norm_text(body.external_key)
    _validate_parent(s, body.kind, body.parent_id)
    _check_org_key(s, key, None)
    org = Organization(name=body.name.strip(), kind=body.kind, parent_id=body.parent_id, external_key=key)
    stamp_new(org, actor_id)
    s.add(org)
    s.flush()
    audit(s, "org.create", "organization", org.id, actor_id, {"name": org.name})
    mark_export(s, "master")
    return ser_org(org)


def patch_org(s: Session, org_id: str, body: OrgPatch, actor_id: str) -> dict:
    org = get_or_404(s, Organization, org_id, "조직")
    check_revision(org, body.expected_revision, "조직")
    before = ser_org(org)
    if body.name is not None:
        org.name = body.name.strip()
    if "parent_id" in body.model_fields_set:
        _validate_parent(s, org.kind, body.parent_id, org.id)
        org.parent_id = body.parent_id
    if "external_key" in body.model_fields_set:
        key = norm_text(body.external_key)
        _check_org_key(s, key, org.id)
        org.external_key = key
    if body.active is not None:
        org.active = body.active
    bump(org, actor_id)
    s.flush()
    audit(s, "org.update", "organization", org.id, actor_id, {"before": before, "after": ser_org(org)})
    mark_export(s, "master")
    return ser_org(org)


# ── 사용자 ──────────────────────────────────────────────────────────────────

def _require_team(s: Session, team_id: str) -> Organization:
    team = s.get(Organization, team_id)
    if team is None or team.deleted_at is not None or team.kind != "team":
        raise validation("소속 팀을 찾을 수 없습니다.", [{"field": "teamId", "code": "NOT_FOUND", "message": "팀을 선택해 주세요."}])
    return team


def _check_user_unique(s: Session, employee_number: str | None, external_key: str | None, self_id: str | None) -> None:
    for col, val, code, msg in ((User.employee_number, employee_number, "DUPLICATE_EMPLOYEE_NUMBER", "이미 등록된 사번입니다."),
                                (User.external_key, external_key, "DUPLICATE_EXTERNAL_KEY", "이미 사용 중인 사용자 코드입니다.")):
        if val is None:
            continue
        q = select(User.id).where(col == val)
        if self_id:
            q = q.where(User.id != self_id)
        if s.execute(q).first():
            raise conflict(code, msg)


def _user_ctx(s: Session, u: User) -> dict:
    team = s.get(Organization, u.team_id)
    division = s.get(Organization, team.parent_id) if team and team.parent_id else None
    return ser_user(u, team, division)


def list_users(s: Session, team_id: str | None, division_id: str | None, active: bool | None, q: str | None,
               limit: int, cursor: str | None) -> dict:
    stmt = select(User).where(User.deleted_at.is_(None)).order_by(User.name, User.id)
    if team_id:
        stmt = stmt.where(User.team_id == team_id)
    if division_id:
        stmt = stmt.where(User.team_id.in_(select(Organization.id).where(Organization.parent_id == division_id)))
    if active is not None:
        stmt = stmt.where(User.active.is_(active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.name.like(like), User.employee_number.like(like)))
    rows, nxt = paginate(s, stmt, limit, cursor)
    return {"items": [_user_ctx(s, u) for u in rows], "nextCursor": nxt}


def get_user(s: Session, user_id: str) -> dict:
    return _user_ctx(s, get_or_404(s, User, user_id, "사용자"))


def create_user(s: Session, body: UserCreate, actor_id: str | None) -> dict:
    _require_team(s, body.team_id)
    emp, ext = norm_text(body.employee_number), norm_text(body.external_key)
    _check_user_unique(s, emp, ext, None)
    u = User(name=body.name.strip(), team_id=body.team_id, employee_number=emp, external_key=ext)
    stamp_new(u, actor_id)
    s.add(u)
    s.flush()
    audit(s, "user.create", "user", u.id, actor_id, {"name": u.name})
    mark_export(s, "master")
    return _user_ctx(s, u)


def patch_user(s: Session, user_id: str, body: UserPatch, actor_id: str) -> dict:
    u = get_or_404(s, User, user_id, "사용자")
    check_revision(u, body.expected_revision, "사용자")
    before = ser_user(u)
    if body.name is not None:
        u.name = body.name.strip()
    if body.team_id is not None:
        _require_team(s, body.team_id)
        u.team_id = body.team_id
    emp = norm_text(body.employee_number) if "employee_number" in body.model_fields_set else u.employee_number
    ext = norm_text(body.external_key) if "external_key" in body.model_fields_set else u.external_key
    _check_user_unique(s, emp, ext, u.id)
    u.employee_number, u.external_key = emp, ext
    if body.active is not None:
        u.active = body.active
    bump(u, actor_id)
    s.flush()
    audit(s, "user.update", "user", u.id, actor_id, {"before": before, "after": ser_user(u)})
    mark_export(s, "master")
    return _user_ctx(s, u)


def count_users(s: Session) -> int:
    return s.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None))).scalar_one()
