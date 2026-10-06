"""보고 자료(월간 종합·경영진 1장 요약) EXAONE 프롬프트 변수 만들기 (설계 단계).

Rule이 기준정보·weekly·cumulative에서 사실과 계산값을 정리해 넘기고, AI는 정해진 칸의 문장만 쓴다.
분량 예산은 장표 칸 크기에서 정했다 (docs/보고자료_양식_분석.md 4장).
렌더러는 다음 단계에서 만든다. 지금은 프롬프트 확인·EXAONE 수동 시험용이다.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import prompt_vars as pv
from . import sources
from .worklog import is_managed, overlay_snapshot
from .codes import CodeTable
from .core import load_json, render_prompt, week_range
from .ppt.milestones import apply_history, delay_days, load_prior_weeklies, mmdd

REPORT_RULES = "prompts/report/report_common_rules.txt"

# 칸별 분량 (가중 글자 수, 한글 1·영문/숫자 0.55)
MONTHLY_BUDGET = {"head_max": 100, "comment_max": 40, "body_max": 60,
                  "highlight_max_items": 4, "risk_max_items": 3, "request_max_items": 3}
EXEC_BUDGET = {"title_max": 30, "head_max": 100, "bc_items": 3, "bc_max": 110, "emphasis_max": 3,
               "subtitle_max": 25, "body_max": 60, "left_max_items": 6, "right_max_items": 5}


def month_weeks(year: int, month: int) -> list[str]:
    """그 달에 속하는 ISO 주차 (목요일이 그 달에 있는 주)."""
    day = date(year, month, 1)
    day += timedelta(days=(3 - day.weekday()) % 7)  # 첫 목요일
    weeks = []
    while day.month == month:
        iso = day.isocalendar()
        weeks.append(f"{iso[0]}-W{iso[1]:02d}")
        day += timedelta(days=7)
    return weeks


def find_derived(kind: str, project_id: str, week: str, dirs: list[Path]) -> dict[str, Any] | None:
    for base in dirs:
        path = base / f"data/derived/{kind}/{project_id}/{week}.json"
        if path.exists():
            return load_json(path)
    return None


def latest_cumulative(project_id: str, week: str, dirs: list[Path]) -> dict[str, Any] | None:
    """week 이전(포함) 가장 최근 누적 요약."""
    candidates = []
    for base in dirs:
        candidates += [p for p in (base / f"data/derived/cumulative/{project_id}").glob("*.json") if p.stem <= week]
    return load_json(max(candidates, key=lambda p: p.stem)) if candidates else None


def current_project(project: dict[str, Any], week: str, dirs: list[Path]) -> dict[str, Any]:
    """기준정보 위에 week까지의 일정 변화를 덧씌운 상태 (주간 PPT와 같은 규칙).

    WorkLog 관리 과제는 week까지 중 가장 최근 주간 정리본의 일정 snapshot을 쓴다 (없으면 현재 값).
    """
    after = f"{week[:6]}{int(week[6:]) + 1:02d}"  # week 포함
    weeklies = load_prior_weeklies(project["project_id"], after, *dirs)
    if is_managed(project):
        snaps = [w for w in sorted(weeklies, key=lambda w: w["week"]) if w.get("milestone_snapshot")]
        return overlay_snapshot(project, snaps[-1]["milestone_snapshot"]) if snaps else project
    return apply_history(project, weeklies, {"week": after, "milestone_updates": []})[0]


def kpi_lines(project: dict[str, Any]) -> str:
    lines = []
    for kpi in project.get("kpis", []):
        latest = kpi["actuals"][-1] if kpi.get("actuals") else None
        now = f"{latest['value']}{kpi['unit']} ({latest['period']})" if latest else "실적 없음"
        target = f", 목표 {kpi['target']}{kpi['unit']}" if kpi.get("target") is not None else ""
        lines.append(f"  - {kpi['name']}: {kpi['baseline']}{kpi['unit']} → {now}{target}  [근거: {project['project_id']}]")
    return "\n".join(lines) or "  - 없음"


def schedule_note(project: dict[str, Any]) -> str:
    """계획이 Baseline보다 늦은 미완료 단계 (코드 계산값)."""
    late = []
    for m in project["milestones"]:
        if m.get("status") == "완료" or not m.get("plan") or not m.get("baseline"):
            continue
        days = delay_days(m["baseline"], m["plan"])
        if days > 0:
            late.append(f"{m['name']} 계획 {mmdd(m['plan'])} (+{days}일)")
    return ", ".join(late) or "지연 단계 없음"


def project_line(project: dict[str, Any]) -> str:
    kpi = project["kpis"][0] if project.get("kpis") else None
    kpi_text = ""
    if kpi:
        latest = f"{kpi['actuals'][-1]['value']}{kpi['unit']}" if kpi.get("actuals") else "실적 없음"
        kpi_text = f" | KPI {kpi['name']} {kpi['baseline']}{kpi['unit']} → {latest}"
    return (f"- {project['project_id']} | {project['name']} | 상태 {project['status']}·{project.get('health') or '-'}"
            f" | 목표 {project['period'].get('target_text') or project['period']['target']} | {schedule_note(project)}{kpi_text}"
            f"  [근거: {project['project_id']}]")


def weekly_block(project_id: str, week: str, weekly: dict[str, Any]) -> str:
    start, end = week_range(week)
    head = f"■ {project_id} {week} ({start.month}/{start.day}~{end.month}/{end.day})"
    return "\n".join([head, pv.prev_weekly_lines(weekly)])


def monthly_variables(root: Path, project_ids: list[str], year: int, month: int, dirs: list[Path] | None = None,
                      org: str | None = None) -> dict[str, Any]:
    dirs = dirs or [root]
    weeks = month_weeks(year, month)
    projects = [current_project(sources.load_project(root, pid), weeks[-1], dirs) for pid in project_ids]
    weekly_blocks, cumulative_blocks = [], []
    for project in projects:
        pid = project["project_id"]
        for week in weeks:
            weekly = find_derived("weekly", pid, week, dirs)
            if weekly:
                weekly_blocks.append(weekly_block(pid, week, weekly))
        cumulative = latest_cumulative(pid, weeks[-1], dirs)
        if cumulative:
            cumulative_blocks.append(f"■ {pid} ({cumulative['as_of_week']} 기준)\n" + pv.cumulative_lines(cumulative["items"]))
    return {**MONTHLY_BUDGET,
            "org": org or projects[0]["org"]["group"], "month_label": f"’{year % 100}.{month}월",
            "week_span": f"{weeks[0][5:]}~{weeks[-1][5:]}",
            "project_lines": "\n".join(project_line(p) for p in projects),
            "weekly_blocks": "\n\n".join(weekly_blocks) or "없음",
            "cumulative_blocks": "\n\n".join(cumulative_blocks) or "없음"}


def exec_variables(root: Path, project_id: str, as_of_week: str, dirs: list[Path] | None = None,
                   recent_weeks: int = 4) -> dict[str, Any]:
    dirs = dirs or [root]
    master = sources.load_project(root, project_id)
    project = current_project(master, as_of_week, dirs)
    codes = CodeTable.load(root)
    blocks = []
    week = as_of_week
    for _ in range(recent_weeks):
        weekly = find_derived("weekly", project_id, week, dirs)
        if weekly:
            blocks.insert(0, weekly_block(project_id, week, weekly))
        start, _end = week_range(week)
        iso = (start - timedelta(days=7)).isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"
    cumulative = latest_cumulative(project_id, as_of_week, dirs) or {"items": [], "pinned_facts": [], "as_of_week": "-"}
    period = project["period"]
    return {**EXEC_BUDGET,
            "project_id": project_id, "project_name": project["name"],
            "org": f"{project['org']['group']} {project['org']['team']}",
            "period": f"{period['start']} ~ {period['target']}", "status": project["status"], "health": project.get("health") or "-",
            "background": project["background"], "purpose": project["purpose"], "kpi_lines": kpi_lines(project),
            "milestone_lines": pv.milestone_lines(project["milestones"], codes), "as_of_week": cumulative["as_of_week"],
            "cumulative_lines": pv.cumulative_lines(cumulative["items"]),
            "pinned_lines": pv.cumulative_lines(cumulative.get("pinned_facts", [])),
            "weekly_blocks": "\n\n".join(blocks) or "없음"}


def render_report_prompt(root: Path, kind: str, variables: dict[str, Any]) -> tuple[str, str]:
    """kind: report_monthly | report_exec_summary. 공통 규칙은 prompts/report/report_common_rules.txt."""
    rules = (root / REPORT_RULES).read_text(encoding="utf-8")
    return render_prompt(root, f"report/{kind}", {"report_rules": rules, **variables})


# ---------------------------------------------------------------- 응답 검사 (렌더러에서 재사용할 규칙)

# 칸 → (분량 키, 문체) : 문체 "경어체" = 완결문 "~니다", "개조식" = "~니다"로 끝나지 않음
REPORT_SLOTS = {
    "report_monthly": {"head_message": ("head_max", "경어체"), "project_comments": ("comment_max", "개조식"),
                       "highlights": ("body_max", "개조식"), "risks": ("body_max", "개조식"), "requests": ("body_max", "개조식")},
    "report_exec_summary": {"title": ("title_max", "개조식"), "head_message": ("head_max", "경어체"),
                            "background_conclusion": ("bc_max", "경어체"), "left_title": ("subtitle_max", "개조식"),
                            "left_items": ("body_max", "개조식"), "right_title": ("subtitle_max", "개조식"),
                            "right_items": ("body_max", "개조식")},
}


def report_style_problems(kind: str, payload: dict[str, Any]) -> list[str]:
    """칸별 분량·문체·강조 구절 검사. 수치·날짜·근거 ID는 validate.check_item으로 따로 검사한다."""
    from .textmetrics import is_polite, weighted_length

    budget = MONTHLY_BUDGET if kind == "report_monthly" else EXEC_BUDGET
    problems = []
    for slot, (limit_key, style) in REPORT_SLOTS[kind].items():
        value = payload.get(slot)
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            text = item["text"]
            where = f"{slot}[{index}]" if isinstance(value, list) else slot
            if weighted_length(text) > budget[limit_key]:
                problems.append(f"{where}: {weighted_length(text):.1f}자 > {budget[limit_key]}자")
            if style == "경어체" and not is_polite(text):
                problems.append(f"{where}: 경어체 완결문이 아님")
            if style == "개조식" and is_polite(text):
                problems.append(f"{where}: 본문은 개조식 (\"~니다\"로 끝내지 않음)")
    if kind == "report_exec_summary":
        joined = " ".join(item["text"] for item in payload.get("background_conclusion", []))
        for phrase in payload.get("emphasis", []):
            if phrase not in joined:
                problems.append(f"emphasis: '{phrase}'가 보고 배경 및 결론 문장에 없음")
    return problems
