"""기준정보 + weekly + cumulative → SlideContent (Rule만 사용, AI 호출 없음)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ..codes import CodeTable, PeopleTable
from ..core import week_range
from ..validate import extract_tokens
from .milestones import format_row, layout_milestones
from .model import BodyItem, Para, Run, Section, SlideContent

SECTION_SPEC = (
    ("cumulative", "진행 현황 – 누적 요약", 8),
    ("progress", "진행 현황 – 금주 변경", 7),
    ("next_plan", "향후 계획", 3),
    ("issues", "이슈·지원 요청", 2),
)
NO_ISSUE = "금주에는 특이사항이 없습니다"
NO_PROGRESS = "금주에는 변경 사항이 없습니다"
NO_PLAN = "향후 계획은 해당 사항이 없습니다"
MAX_MS_ROWS = 9


def norm_text(text: str) -> str:
    """중복 판정용 정규화 (공백·괄호·구두점 차이 무시)."""
    return re.sub(r"[\s\-–·,.()（）~]+", "", text)


def key_numbers(text: str) -> set[str]:
    """핵심 측정값(소수·퍼센트) 집합. 고정 사실이 누적 항목에 이미 들어 있는지 판단할 때 쓴다."""
    return {n.rstrip("%") for n in extract_tokens(text).numbers if "." in n or n.endswith("%")}


def md(day: date) -> str:
    return f"{day.month}/{day.day}"


def updated_at_label(iso: str) -> str:
    stamp = datetime.fromisoformat(iso)
    return f"업데이트 시간 : {stamp.month}/{stamp.day} {stamp.hour}시"


def target_text(project: dict[str, Any]) -> str:
    period = project["period"]
    if period.get("target_text"):
        return period["target_text"]
    target = date.fromisoformat(period["target"])
    return f"'{target.year % 100:02d}.{target.month:02d}"


def overdue_notes(project: dict[str, Any], codes: CodeTable, changed: set[tuple[str, str]]) -> list[Run]:
    """과제 목표일을 넘는 미완료 단계 → 일정 칸 병기 (예: "(북미 10월초)").

    plan이 목표일보다 늦거나, plan_text의 "N월"이 목표 월보다 늦은 단계만 고른다 (추정하지 않음).
    이번 주 plan/plan_text가 바뀐 단계는 파란색.
    """
    target = date.fromisoformat(project["period"]["target"])
    runs: list[Run] = []
    for m in sorted(project["milestones"], key=lambda x: x["order"]):
        if m["status"] in {"완료", "취소"}:
            continue
        label = None
        if m.get("plan_text"):
            month = re.search(r"(\d{1,2})\s*월", m["plan_text"])
            year = int((m.get("plan") or m.get("baseline") or project["period"]["target"])[:4])
            if month and (year, int(month[1])) > (target.year, target.month):
                label = m["plan_text"]
        elif m.get("plan") and date.fromisoformat(m["plan"]) > target:
            label = md(date.fromisoformat(m["plan"]))
        if label:
            scope = re.split(r"[·,]", codes.scope_label(m["scope"]))[0].strip()
            blue = bool({(m["milestone_id"], "plan"), (m["milestone_id"], "plan_text")} & changed)
            runs.append(Run(f"({scope} {label})", blue=blue))
    return runs


def cumulative_items(cumulative: dict[str, Any], notes: list[str]) -> list[BodyItem]:
    """누적 요약 + 본문에 빠진 고정 사실(pinned_facts). 모두 검정."""
    items = [BodyItem(v["text"], list(v.get("source_ids", [])), False, v.get("kind", "fact")) for v in cumulative.get("items", [])]
    seen = [norm_text(i.text) for i in items]
    seen_numbers = [key_numbers(i.text) for i in items]
    for fact in cumulative.get("pinned_facts", []):
        key = norm_text(fact["text"])
        numbers = key_numbers(fact["text"])
        if any(key == s or key in s for s in seen) or (numbers and any(numbers <= n for n in seen_numbers)):
            notes.append(f"고정 사실은 누적 요약 항목에 이미 반영됨: {fact['text']}")
            continue
        items.append(BodyItem(fact["text"], list(fact.get("source_ids", [])), False, fact.get("kind", "fact")))
        seen.append(key)
        notes.append(f"고정 사실을 누적 요약에 추가: {fact['text']}")
    return items


def weekly_items(values: list[dict[str, Any]], default_kind: str) -> list[BodyItem]:
    return [BodyItem(v["text"], list(v.get("source_ids", [])), bool(v.get("changed")), v.get("kind", default_kind), bool(v.get("changed")))
            for v in values]


def build_content(project: dict[str, Any], weekly: dict[str, Any], cumulative: dict[str, Any], codes: CodeTable,
                  changed: set[tuple[str, str]], *, project_index: int = 1, project_total: int = 1,
                  people: PeopleTable | None = None) -> SlideContent:
    """project는 milestone_updates가 이미 덧씌워진 메모리 복사본이다."""
    notes: list[str] = []
    start, end = week_range(weekly["week"])
    week_label = f"W{weekly['week'][-2:]}"

    rows, overflow = layout_milestones(project["milestones"], MAX_MS_ROWS, codes, changed)
    if overflow:
        notes.append(f"마일스톤 {len(rows) + len(overflow)}행: 완료 하위 행을 접어도 {MAX_MS_ROWS}행 초과 → {len(overflow)}행을 (계속) 장으로 이월")
    for row in rows:
        if row.get("folded_from"):
            notes.append(f"완료 하위 행 접기: {', '.join(row['folded_from'])} → '{row['name']}'")

    # 완성 예시 형식: "[배경/목표]" 제목 줄 + "- 배경. 목적" 한 문단 (기준정보 문장을 고치지 않고 이어 붙임)
    background = project["background"].rstrip(" .")
    body_top = [
        Para([Run("[배경/목표]", bold=True)], "heading"),
        Para([Run(f"- {background}. {project['purpose']}")], "item"),
    ]

    sections = []
    for key, heading, limit in SECTION_SPEC:
        if key == "cumulative":
            items = cumulative_items(cumulative, notes)
        else:
            items = weekly_items(weekly.get(key, []), {"progress": "fact", "next_plan": "plan", "issues": "issue"}[key])
        if not items and key == "issues":
            items = [BodyItem(NO_ISSUE, [], False, "issue")]
        if not items and key == "progress":
            items = [BodyItem(NO_PROGRESS, [], False, "fact")]
        if not items and key == "next_plan":
            items = [BodyItem(NO_PLAN, [], False, "plan")]
        sections.append(Section(key, heading, items, limit))

    people = people or PeopleTable({"people": {}})
    overdue = overdue_notes(project, codes, changed)
    if overdue:
        notes.append("일정 칸 병기(목표일 초과 단계): " + ", ".join(r.text for r in overdue))
    main = {
        "name": Run(project["name"]),
        "target": Run(codes.target_label(project["target"])),
        "week_header": Run(f"금주 진행사항 ({week_label})  ({md(start)}~{md(end)})"),
        "headline": Run(weekly["headline"]["text"], blue=True),  # 한 줄 요약은 매주 새로 작성 → 항상 파란색
        # 목표 일정(검정) + 목표일을 넘는 단계 병기 (이번 주 바뀐 것만 파랑)
        "schedule": [Para([Run(target_text(project) + (" /" if overdue else ""))])] + [Para([r]) for r in overdue],
        "owner": Run("\n".join(people.name(u) for u in dict.fromkeys([project["owner"], *project.get("members", [])]))),
    }
    for part in project["target"]:
        unknown = codes.unknown_codes(part)
        if unknown:
            notes.append(f"대상 코드표 미등록: {', '.join(unknown)} (코드 그대로 표시)")
    missing = people.missing([project["owner"], *project.get("members", [])])
    if missing:
        notes.append(f"config/people.json에 없는 사용자 ID는 그대로 표시: {', '.join(missing)}")

    return SlideContent(
        project_id=project["project_id"],
        week=weekly["week"],
        title=f"1. 과제 진행 현황_{project['org']['team']}",
        pjt_name=f"■ {project['name']} ({project_index}/{project_total})",
        author=f"작성자 : {people.name_with_title(project['owner'])}",
        updated_at=updated_at_label(weekly["meta"]["updated_at"]),
        main=main,
        body_top=body_top,
        ms_rows=[format_row(m, codes, changed) for m in rows],
        ms_overflow=[format_row(m, codes, changed) for m in overflow],
        sections=sections,
        notes=notes,
    )
