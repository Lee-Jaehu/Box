"""보고 자료 생성: 프롬프트 → EXAONE(또는 mock·붙여넣기 응답) → 검사·칸 단위 대체 → 템플릿 채우기 → 재검사.

- 경영진 1장 요약: generate_exec_summary (과제 1개, 기준 주차)
- 월간 종합 보고: generate_monthly (여러 과제, 연·월)
mock 응답 이름: prompts/mock_responses/{kind}__{scope}__{period}.json
  (exec: scope=과제 ID, period=주차 / monthly: scope=ALL 등, period=YYYY-MM)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..ai import ExaoneClient
from ..codes import CodeTable, PeopleTable
from .. import sources
from ..core import KST, load_json
from ..fonts import load_fonts
from ..ppt.model import Para, Run
from ..report_vars import (current_project, exec_variables, find_derived, latest_cumulative, month_weeks,
                           monthly_variables, render_report_prompt)
from .checks import check_report
from .content import NOTE, Cell, kpi_rows, late_stages, org_date, project_row
from .render import (OVERVIEW_BOTTOM_IN, SlideFill, find_report_template, inspect_report, open_report_template,
                     paginate_rows, render_report)

BRACKET_RE = re.compile(r"^(\[[^\]]*\])(.*)$")


# ---------------------------------------------------------------- 문단 만들기

def item_paras(items: list[dict[str, Any]]) -> list[Para]:
    """개조식 항목: "[ 소제목 ] 내용"은 소제목만 굵게, "▶ 요청:"도 굵게."""
    paras = []
    for item in items:
        text = item["text"]
        match = BRACKET_RE.match(text)
        if match:
            paras.append(Para([Run(match.group(1), bold=True), Run(match.group(2))]))
        elif text.startswith("▶"):
            head, _, rest = text.partition(":")
            paras.append(Para([Run(head + (":" if rest else ""), bold=True), Run(rest)]))
        else:
            paras.append(Para([Run(text)]))
    return paras or [Para([Run("- 해당 사항 없음")])]


def emphasis_runs(text: str, phrases: list[str]) -> list[Run]:
    """굵은 문장 안에서 강조 구절만 노랑 형광."""
    spans = sorted((text.find(p), len(p)) for p in phrases if p and p in text)
    runs, pos = [], 0
    for start, length in spans:
        if start < pos:
            continue
        if start > pos:
            runs.append(Run(text[pos:start], bold=True))
        runs.append(Run(text[start:start + length], bold=True, highlight=True))
        pos = start + length
    if pos < len(text):
        runs.append(Run(text[pos:], bold=True))
    return runs


def bold_line(text: str, color: str | None = None) -> list[Para]:
    return [Para([Run(text, bold=True, color=color)])]


def plain_lines(text: str, color: str | None = None) -> list[Para]:
    return [Para([Run(line, color=color)]) for line in text.split("\n")]


# ---------------------------------------------------------------- 공통

def _client(root: Path, client: ExaoneClient | None, mode: str) -> ExaoneClient:
    return client or ExaoneClient(root, mode)


def _write_check(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> Path:
    lines = [title, ""]
    for heading, items in sections:
        lines.append(f"[{heading}]")
        lines += [f"- {item}" for item in items] or ["- 없음"]
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return path


def _today(today: date | None) -> date:
    return today or datetime.now(KST).date()


# ---------------------------------------------------------------- 경영진 1장 요약

def exec_fallback(project: dict[str, Any], cumulative: dict[str, Any] | None, weekly: dict[str, Any] | None) -> dict[str, Any]:
    """AI 칸이 검사를 통과하지 못할 때 쓰는 Rule 값 (기준정보·누적 요약 문장 그대로)."""
    pid = project["project_id"]
    return {
        "title": {"text": f"{project['name']} 진행 현황", "source_ids": [pid]},
        "head_message": {"text": f"{project['name']} 과제의 진행 현황을 보고드립니다.", "source_ids": [pid]},
        "background_conclusion": [{"text": f"배경: {project['background']}", "source_ids": [pid]},
                                  {"text": f"목적: {project['purpose']}", "source_ids": [pid]},
                                  {"text": "세부 진행 결과는 아래 상세 검토 결과를 참고 부탁드립니다.", "source_ids": [pid]}],
        "emphasis": [],
        "left_title": {"text": "추진 경과 및 성과", "source_ids": [pid]},
        "left_items": [{"text": f"- {v['text']}", "source_ids": v.get("source_ids", [])} for v in (cumulative or {}).get("items", [])[:6]],
        "right_title": {"text": "향후 계획 및 요청 사항", "source_ids": [pid]},
        "right_items": [{"text": f"- {v['text']}", "source_ids": v.get("source_ids", [])} for v in (weekly or {}).get("next_plan", [])[:5]],
    }


def generate_exec_summary(root: Path, project_id: str, week: str, output: Path, *, client: ExaoneClient | None = None,
                          mode: str = "mock", dirs: list[Path] | None = None, template: Path | None = None,
                          today: date | None = None) -> dict[str, Any]:
    client = _client(root, client, mode)
    built = exec_fill(root, project_id, week, client=client, dirs=dirs, today=today)
    fill, notes, schedule, project = built["fill"], built["notes"], built["schedule"], built["project"]
    template = template or find_report_template(root)
    render_notes = render_report(template, [fill], output)
    problems = inspect_report(output, root)
    check = _write_check(output.with_name(f"{output.stem}_check.txt"), f"경영진 1장 요약: {project_id} {project['name']} ({week} 기준)", [
        ("AI 응답 처리 (모델: " + client.model_label + ")", notes),
        ("코드 계산값 (AI 수치 아님)", [f"KPI 변화: {' / '.join(r[0].text + ' ' + r[4].text for r in kpi_rows(project))}", schedule.lstrip("└ ")]),
        ("PPT 재검사", problems or ["통과 (글꼴·영역 경계·글 분량)"]),
        ("처리 내역", render_notes),
    ])
    return {"pptx": output, "check": check, "problems": problems, "notes": notes, "prompt": built["prompt"]}


def exec_fill(root: Path, project_id: str, week: str, *, client: ExaoneClient, dirs: list[Path] | None = None,
              today: date | None = None, response_key: str | None = None, weekly_blocks: str | None = None) -> dict[str, Any]:
    """[Worklog 통합] 경영진 1장 요약 슬라이드 1장의 내용(SlideFill)만 만든다. 여러 과제를 한 파일로 합칠 때 쓴다.

    response_key: AI 응답 구분 키(기본 week, 기간 보고는 기간 키). weekly_blocks: '최근 주간 정리본' 칸을 바꿔 넣을 때(기간 정리본).
    """
    dirs = dirs or [root]
    variables = exec_variables(root, project_id, week, dirs)
    if weekly_blocks is not None:
        variables["weekly_blocks"] = weekly_blocks
    system, user = render_report_prompt(root, "report_exec_summary", variables)
    payload = client.complete("report_exec_summary", project_id, response_key or week, system, user)
    project = current_project(sources.load_project(root, project_id), week, dirs)
    codes = CodeTable.load(root)
    fallback = exec_fallback(project, latest_cumulative(project_id, week, dirs), find_derived("weekly", project_id, week, dirs))
    content, notes = check_report("report_exec_summary", payload, root, user, [project], fallback)

    late = late_stages(project, codes)
    schedule = "└ 일정: " + (", ".join(late) if late else "지연 단계 없음") + " (코드 계산)"
    fill = SlideFill("exec_summary", texts={
        "title": bold_line(content["title"]["text"]),
        "org_date": plain_lines(org_date(project["org"]["team"], _today(today))),
        "head_message": bold_line(content["head_message"]["text"]),
        "background_conclusion": [Para([Run("• ", bold=True)] + emphasis_runs(v["text"], content.get("emphasis", [])))
                                  for v in content["background_conclusion"]],
        "left_title": bold_line(f"[ {content['left_title']['text'].strip('[] ')} ]"),
        "left_items": item_paras(content["left_items"]),
        "right_title": bold_line(f"[ {content['right_title']['text'].strip('[] ')} ]"),
        "right_items": item_paras(content["right_items"]),
        "schedule_note": plain_lines(schedule, NOTE),
    }, tables={"kpi_table": kpi_rows(project)})
    return {"fill": fill, "notes": notes, "schedule": schedule, "project": project, "prompt": f"{system}\n\n{user}"}


# ---------------------------------------------------------------- 월간 종합 보고

def _request_project(request: dict[str, Any], owners: dict[str, str]) -> str:
    for source in request.get("source_ids", []):
        if source in owners:
            return owners[source]
    return "-"


def monthly_fallback(projects: list[dict[str, Any]], month_label: str) -> dict[str, Any]:
    ids = [p["project_id"] for p in projects]
    return {"head_message": {"text": f"{month_label} {len(projects)}개 과제의 진행 현황을 보고드립니다.", "source_ids": ids},
            "project_comments": [{"project_id": pid, "text": "주간 정리본 참조", "source_ids": [pid]} for pid in ids],
            "highlights": [], "risks": [], "requests": []}


def generate_monthly(root: Path, project_ids: list[str], year: int, month: int, output: Path, *,
                     client: ExaoneClient | None = None, mode: str = "mock", dirs: list[Path] | None = None,
                     scope: str = "ALL", template: Path | None = None, today: date | None = None,
                     org: str | None = None) -> dict[str, Any]:
    dirs = dirs or [root]
    period = f"{year}-{month:02d}"
    variables = monthly_variables(root, project_ids, year, month, dirs, org)  # [Worklog 통합] org: 화면에서 고른 조직 이름
    system, user = render_report_prompt(root, "report_monthly", variables)
    client = _client(root, client, mode)
    payload = client.complete("report_monthly", scope, period, system, user)
    weeks = month_weeks(year, month)
    projects = [current_project(sources.load_project(root, pid), weeks[-1], dirs) for pid in project_ids]
    computed = [f"{month}월", f"{len(projects)}개"]  # "9월 6개 과제" 같은 표현의 근거 (코드 계산값)
    content, notes = check_report("report_monthly", payload, root, user, projects, monthly_fallback(projects, variables["month_label"]),
                                  computed)

    people, codes = PeopleTable.load(root), CodeTable.load(root)
    comments = {c["project_id"]: c["text"] for c in content["project_comments"]}
    rows = [project_row(p, people.with_project(p), codes, comments.get(p["project_id"], "")).cells for p in projects]
    owners: dict[str, str] = {}
    for project in projects:
        owners[project["project_id"]] = project["name"]
        for week in weeks:
            weekly = find_derived("weekly", project["project_id"], week, dirs) or {}
            for slot in ("headline", "progress", "next_plan", "issues"):
                for item in (weekly.get(slot) or []) if isinstance(weekly.get(slot), list) else [weekly.get(slot) or {}]:
                    for source in item.get("source_ids", []):
                        owners.setdefault(source, project["name"])
    template = template or find_report_template(root)
    hangul_em = load_fonts(template.parent.resolve()).hangul_em
    pages = paginate_rows(open_report_template(template), rows, hangul_em, OVERVIEW_BOTTOM_IN)
    org = variables["org"]
    title = f"{org} 과제 종합 현황 / {variables['month_label']}"
    head = bold_line(content["head_message"]["text"])
    date_text = plain_lines(org_date(org, _today(today)))
    fills = []
    for index, page_rows in enumerate(pages):
        last = index == len(pages) - 1
        fills.append(SlideFill("monthly_overview", texts={
            "title": bold_line(title + (" (계속)" if index else "")), "org_date": date_text, "head_message": head,
            "highlights": item_paras(content["highlights"]) if last else [Para([Run("- 다음 장에 이어서")])],
            "risks": item_paras(content["risks"]) if last else [Para([Run("- 다음 장에 이어서")])],
        }, tables={"project_table": page_rows}))
    if content["requests"]:
        request_rows = [[Cell(_request_project(r, owners), bold=True), Cell(r["text"]), Cell(r.get("due") or "-"),
                         Cell(r.get("dept") or "-")] for r in content["requests"]]
        fills.append(SlideFill("monthly_requests", texts={
            "title": bold_line(f"의사결정 및 업무협조 요청 / {variables['month_label']}"), "org_date": date_text,
            "head_message": bold_line(f"{variables['month_label']} 의사결정·업무협조 요청 {len(request_rows)}건을 보고드립니다."),
        }, tables={"requests_table": request_rows}))
    render_notes = render_report(template, fills, output)
    if len(pages) > 1:
        render_notes.append(f"과제 {len(rows)}개 → 현황표 {len(pages)}장으로 나눔")
    problems = inspect_report(output, root)
    check = _write_check(output.with_name(f"{output.stem}_check.txt"),
                         f"월간 종합 보고: {org} {variables['month_label']} ({variables['week_span']}), 과제 {len(projects)}개", [
        ("AI 응답 처리 (모델: " + client.model_label + ")", notes),
        ("코드 계산값 (AI 수치 아님)", [f"{p['project_id']}: {', '.join(late_stages(p, codes)) or '지연 단계 없음'}" for p in projects]),
        ("PPT 재검사", problems or ["통과 (글꼴·영역 경계·글 분량)"]),
        ("처리 내역", render_notes),
    ])
    return {"pptx": output, "check": check, "problems": problems, "notes": notes, "prompt": f"{system}\n\n{user}"}
