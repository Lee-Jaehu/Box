"""기준정보 + weekly + cumulative → SlideContent (Rule만 사용, AI 호출 없음)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ..codes import CodeTable
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
NO_ISSUE = "특이사항 없음"
NO_PROGRESS = "금주 변경 사항 없음"
NO_PLAN = "해당 없음"
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
    return f"업데이트 시간 : {stamp.month}/{stamp.day} {stamp.hour:02d}시"


def target_text(project: dict[str, Any]) -> str:
    period = project["period"]
    if period.get("target_text"):
        return period["target_text"]
    target = date.fromisoformat(period["target"])
    return f"'{target.year % 100:02d}.{target.month:02d}"


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
                  changed: set[tuple[str, str]], *, project_index: int = 1, project_total: int = 1) -> SlideContent:
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

    body_top = [
        Para([Run("[배경] ", bold=True), Run(project["background"])]),
        Para([Run("[목표] ", bold=True), Run(project["purpose"])]),
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

    main = {
        "name": Run(project["name"]),
        "target": Run(codes.target_label(project["target"])),
        "week_header": Run(f"금주 진행사항 ({week_label})  ({md(start)}~{md(end)})"),
        "headline": Run(weekly["headline"]["text"], blue=True),  # 한 줄 요약은 매주 새로 작성 → 항상 파란색
        "schedule": Run(target_text(project)),  # 기준정보 기간 변경은 weekly 계약에 없음 → 검정
        "owner": Run(project["owner"]),
    }
    for part in project["target"]:
        unknown = codes.unknown_codes(part)
        if unknown:
            notes.append(f"대상 코드표 미등록: {', '.join(unknown)} (코드 그대로 표시)")
    notes.append("작성자 이름·직급은 기준정보에 없어 사용자 ID로 표시")

    return SlideContent(
        project_id=project["project_id"],
        week=weekly["week"],
        title=f"1. 과제 진행 현황_{project['org']['team']}",
        pjt_name=f"■ {project['name']} ({project_index}/{project_total})",
        author=f"작성자 : {project['owner']}",
        updated_at=updated_at_label(weekly["meta"]["updated_at"]),
        main=main,
        body_top=body_top,
        ms_rows=[format_row(m, codes, changed) for m in rows],
        ms_overflow=[format_row(m, codes, changed) for m in overflow],
        sections=sections,
        notes=notes,
    )
