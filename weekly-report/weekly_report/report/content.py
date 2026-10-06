"""보고 자료의 Rule 값: 과제 현황 행, KPI 표, 일정 메모 (AI가 만들지 않는 숫자·색).

색 규칙 (장표모음집): 개선 = 파랑 0000CC, 악화 = 빨강 C00000, 보조 설명 = 녹색 006600.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ..codes import CodeTable, PeopleTable
from ..ppt.milestones import delay_days, mmdd

IMPROVE, WORSE, NOTE = "0000CC", "C00000", "006600"
# 상태·건강도 칸 배경 (주간 마일스톤 상태 색과 같은 계열)
HEALTH_FILL = {"정상": "E2EFDA", "주의": "FFF2CC", "지연": "FBE2E2", "판단 불가": "EDEDED"}
STATUS_FILL = {"완료": "E7E7E7", "보류": "EDEDED", "취소": "EDEDED"}


@dataclass
class Cell:
    text: str
    color: str | None = None
    bold: bool = False
    fill: str | None = None


@dataclass
class ProjectRow:
    project_id: str
    cells: list[Cell] = field(default_factory=list)  # 과제 | 담당 | 상태 | 목표 일정 | KPI | 이번 달 주요 내용


def _decimals(value: Any) -> int:
    exponent = Decimal(str(value)).as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def kpi_change(kpi: dict[str, Any]) -> Cell:
    """기준 → 최신 변화량 (코드 계산값). 감소는 "Δ", 증가는 "+", %는 %p. 개선 파랑·악화 빨강."""
    if not kpi.get("actuals"):
        return Cell("-")
    base, latest = Decimal(str(kpi["baseline"])), Decimal(str(kpi["actuals"][-1]["value"]))
    diff = latest - base
    places = max(_decimals(kpi["baseline"]), _decimals(kpi["actuals"][-1]["value"]))
    unit = "%p" if kpi.get("unit") == "%" else (kpi.get("unit") or "")
    magnitude = f"{abs(diff):.{places}f}{unit}"
    if diff == 0:
        return Cell(f"0{unit}")
    better = (diff < 0) == (kpi.get("direction") == "down")
    return Cell(("Δ" if diff < 0 else "+") + magnitude, IMPROVE if better else WORSE, bold=True)


def kpi_rows(project: dict[str, Any]) -> list[list[Cell]]:
    """경영진 1장 요약 KPI 표: 지표 | 기준 | 최신 (기간) | 목표 | 변화."""
    rows = []
    for kpi in project.get("kpis", []):
        unit = kpi.get("unit") or ""
        latest = kpi["actuals"][-1] if kpi.get("actuals") else None
        rows.append([Cell(kpi["name"]), Cell(f"{kpi['baseline']}{unit}"),
                     Cell(f"{latest['value']}{unit} ({latest['period'][5:]})" if latest else "실적 없음"),
                     Cell(f"{kpi['target']}{unit}" if kpi.get("target") is not None else "-"), kpi_change(kpi)])
    return rows or [[Cell("KPI 없음"), Cell("-"), Cell("-"), Cell("-"), Cell("-")]]


def late_stages(project: dict[str, Any], codes: CodeTable) -> list[str]:
    """계획이 Baseline보다 늦은 미완료 단계: "수평전개(북미·조립) 10/13 (+18일)" (코드 계산값)."""
    late = []
    for m in project["milestones"]:
        if m.get("status") in ("완료", "취소") or not m.get("plan") or not m.get("baseline"):
            continue
        days = delay_days(m["baseline"], m["plan"])
        if days > 0:
            scope = codes.scope_label(m["scope"]) if m.get("scope") not in (None, "common") else ""
            label = f"{m['name']}({scope})" if scope else m["name"]
            late.append(f"{label} {mmdd(m['plan'])} (+{days}일)")
    return late


def schedule_cell(project: dict[str, Any], codes: CodeTable) -> Cell:
    period = project["period"]
    target = period.get("target_text") or mmdd(period["target"])
    late = late_stages(project, codes)
    overdue = project.get("status") not in ("완료", "취소") and period.get("target") and late
    text = f"{target}" + (f"\n└ {late[0]}" if late else "")
    return Cell(text, WORSE if overdue else None)


def health_cell(project: dict[str, Any]) -> Cell:
    status, health = project.get("status") or "-", project.get("health") or "-"
    fill = STATUS_FILL.get(status) or HEALTH_FILL.get(health)
    return Cell(f"{status}\n({health})" if health != "-" else status, fill=fill)


def kpi_cell(project: dict[str, Any]) -> Cell:
    if not project.get("kpis"):
        return Cell("-")
    kpi = project["kpis"][0]
    unit = kpi.get("unit") or ""
    latest = kpi["actuals"][-1]["value"] if kpi.get("actuals") else None
    change = kpi_change(kpi)
    text = f"{kpi['name']}\n{kpi['baseline']}{unit} → {latest}{unit}" if latest is not None else f"{kpi['name']}\n실적 없음"
    return Cell(text + (f" ({change.text})" if latest is not None else ""), change.color)


def project_row(project: dict[str, Any], people: PeopleTable, codes: CodeTable, comment: str = "") -> ProjectRow:
    owners = [project["owner"]] + [m for m in project.get("members", []) if m != project["owner"]]
    return ProjectRow(project["project_id"], [
        Cell(project["name"], bold=True), Cell(", ".join(people.name(p) for p in owners[:2]) + (" 외" if len(owners) > 2 else "")),
        health_cell(project), schedule_cell(project, codes), kpi_cell(project), Cell(comment)])


def org_date(org_text: str, today: date) -> str:
    return f"{org_text}\n{today.year}. {today.month}. {today.day}"
