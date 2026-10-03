"""마일스톤 덧씌우기·표시 형식·행 접기 (Rule 기반, PPT 비의존)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..codes import CodeTable
from ..validate import milestone_update_problem

STATUS_FILL = {"완료": "E7E7E7", "진행": "DDEBF7", "지연": "FBE2E2", "예정": "FFFFFF", "보류": "FFFFFF", "취소": "FFFFFF"}
EMPTY = "–"


def apply_updates(project: dict[str, Any], weekly: dict[str, Any]) -> tuple[dict[str, Any], list[str], set[tuple[str, str]]]:
    """weekly.milestone_updates를 기준정보의 메모리 복사본에만 적용한다 (baseline·원본 불변).

    반환: (적용된 복사본, 적용하지 않은 사유 목록, 이번 주 바뀐 (milestone_id, field) 집합)
    """
    result, warnings, changed = deepcopy(project), [], set()
    milestones = {m["milestone_id"]: m for m in result["milestones"]}
    for index, update in enumerate(weekly.get("milestone_updates", [])):
        problem = milestone_update_problem(update, set(milestones))
        if problem:
            warnings.append(f"milestone_updates[{index}]: {problem}; 적용하지 않음")
            continue
        mid, fld, value = update["milestone_id"], update["field"], update["to"]
        if (mid, fld) in changed:
            warnings.append(f"milestone_updates[{index}]: {mid}.{fld} 중복 변경 → 마지막 값 적용")
        if milestones[mid].get(fld) == value:
            warnings.append(f"milestone_updates[{index}]: {mid}.{fld} 값이 기존과 같음 → 변경 표시 안 함")
            continue
        milestones[mid][fld] = value
        changed.add((mid, fld))
    for mid, fld in sorted(changed):
        m = milestones[mid]
        if fld == "plan" and m.get("plan_text") and (mid, "plan_text") not in changed:
            warnings.append(f"{mid}: 계획일이 바뀌었으나 기존 plan_text '{m['plan_text']}'가 표시 우선")
    return result, warnings, changed


def mmdd(iso: str | None) -> str:
    if not iso:
        return EMPTY
    return f"{iso[5:7]}/{iso[8:10]}"


def stage_label(milestone_id: str) -> str:
    """M4 → "4.", M6-1 → "6-1." """
    return milestone_id.lstrip("M") + "."


def delay_days(baseline: str, plan: str) -> int:
    return (date.fromisoformat(plan) - date.fromisoformat(baseline)).days


@dataclass
class MsRow:
    milestone_id: str
    cells: list[str]
    blue: list[bool]
    status: str
    computed: list[str] = field(default_factory=list)  # 코드가 계산한 값 (예: 지연 일수)
    folded_from: list[str] = field(default_factory=list)

    @property
    def fill(self) -> str:
        return STATUS_FILL.get(self.status, "FFFFFF")


def plan_cell(m: dict[str, Any]) -> tuple[str, list[str]]:
    """계획 칸: plan_text 우선, 그다음 plan≠baseline이면 "MM/DD (+n)"."""
    if m.get("plan_text"):
        return m["plan_text"], []
    plan, baseline = m.get("plan"), m.get("baseline")
    if plan and baseline and plan != baseline:
        n = delay_days(baseline, plan)
        return f"{mmdd(plan)} ({n:+d})", [f"{m['milestone_id']} 지연 일수 {n:+d} (계획-Baseline 계산값)"]
    return mmdd(plan), []


def format_row(m: dict[str, Any], codes: CodeTable, changed: set[tuple[str, str]]) -> MsRow:
    mid = m["milestone_id"]
    plan, computed = plan_cell(m)
    cells = [
        f"{stage_label(mid)} {m['name']}",
        m.get("scope_label") or codes.scope_label(m["scope"]),
        mmdd(m.get("baseline")),
        plan,
        mmdd(m.get("actual")),
        m["status"],
        m.get("note") or "",
    ]
    fields = [(), (), (), ("plan", "plan_text"), ("actual",), ("status",), ("note",)]
    flagged = set(m.get("changed_fields", [])) | {f for (i, f) in changed if i == mid}
    blue = [bool(flagged & set(f)) for f in fields]
    return MsRow(mid, cells, blue, m["status"], computed, list(m.get("folded_from", [])))


def _fold(group: list[dict[str, Any]], codes: CodeTable, changed: set[tuple[str, str]]) -> dict[str, Any]:
    first = group[0]
    def same(key: str) -> str | None:
        values = {g.get(key) for g in group}
        return values.pop() if len(values) == 1 else None
    actuals = [g["actual"] for g in group if g.get("actual")]
    folded = deepcopy(first)
    folded.update({
        "milestone_id": first["parent_id"],
        "name": f"{first['name']} 완료 {len(group)}개 사이트",
        "scope_label": ", ".join(codes.scope_label(g["scope"]) for g in group),
        "baseline": same("baseline"),
        "plan": same("plan"),
        "plan_text": None,
        "actual": max(actuals) if actuals else None,
        "note": None,
        "folded_from": [g["milestone_id"] for g in group],
        "changed_fields": sorted({f for g in group for (i, f) in changed if i == g["milestone_id"]}),
    })
    return folded


def collapse_milestones(rows: list[dict[str, Any]], maximum: int = 9, codes: CodeTable | None = None,
                        changed: set[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """maximum행을 넘으면 같은 parent_id의 완료 하위 행(2개 이상)을 한 행으로 접는다.

    접을 수 있는 행을 다 접어도 넘치면 그대로 반환한다 (넘친 행은 layout_milestones가 (계속)으로 보낸다).
    """
    codes = codes or CodeTable({})
    changed = changed or set()
    rows = sorted(rows, key=lambda x: x["order"])
    while len(rows) > maximum:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row.get("parent_id") and row["status"] == "완료" and not row.get("folded_from"):
                groups.setdefault(row["parent_id"], []).append(row)
        candidates = [g for g in groups.values() if len(g) >= 2]
        if not candidates:
            break
        group = candidates[0]
        folded = _fold(group, codes, changed)
        ids = {g["milestone_id"] for g in group}
        position = rows.index(group[0])
        rows = [r for r in rows if r["milestone_id"] not in ids]
        rows.insert(position, folded)
    return rows


def layout_milestones(rows: list[dict[str, Any]], maximum: int = 9, codes: CodeTable | None = None,
                      changed: set[tuple[str, str]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(첫 장에 넣을 행, (계속) 장으로 넘길 행). 행을 버리지 않는다."""
    collapsed = collapse_milestones(rows, maximum, codes, changed)
    return collapsed[:maximum], collapsed[maximum:]
