"""WorkLog export(동료가 만든 업무기록 시스템의 JSON) → 내부 project/daily 형식 변환.

- WORKLOG_PROJECT_EXPORT  → 내부 project (schemas/project.schema.json)
- WORKLOG_DAILY_EXPORT    → 내부 daily 목록 (log 1건 = daily 1건, schemas/daily.schema.json)
원본 파일은 읽기만 한다. 값 대응은 config/worklog_mapping.json, 규칙 설명은 docs/WorkLog_연동.md.

결정 사항 (2026-10-04)
- 마일스톤 일정·상태는 WorkLog 값이 기준(milestones_managed). AI 일정 추출은 쓰지 않는다.
- WorkLog에 없는 칸: 주간 PPT '대상' = 팀명, 마일스톤 '적용 범위' = 계획 기간(MM/DD~MM/DD).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .core import load_json

PROJECT_TYPE = "WORKLOG_PROJECT_EXPORT"
DAILY_TYPE = "WORKLOG_DAILY_EXPORT"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
EMPTY = "-"


class WorklogError(ValueError):
    """WorkLog export를 변환할 수 없음."""


def load_mapping(root: Path) -> dict[str, Any]:
    return load_json(root / "config/worklog_mapping.json")


# ---------------------------------------------------------------- tiptap → 텍스트

def _inline(node: dict[str, Any]) -> str:
    if node.get("type") == "text":
        return node.get("text", "")
    if node.get("type") == "hardBreak":
        return "\n"
    return "".join(_inline(child) for child in node.get("content", []) or [])


def _blocks(nodes: list[dict[str, Any]], depth: int = 0) -> list[tuple[int, str | None, str]]:
    """(들여쓰기 깊이, 목록 표시(None/"-"/번호), 문장) 목록."""
    out: list[tuple[int, str | None, str]] = []
    for node in nodes or []:
        kind = node.get("type")
        if kind in ("bulletList", "orderedList", "taskList"):
            start = (node.get("attrs") or {}).get("start") or 1
            for index, item in enumerate(node.get("content", []) or []):
                marker = f"{start + index}." if kind == "orderedList" else "-"
                inner = _blocks(item.get("content", []), depth + 1)
                if inner and inner[0][1] is None and inner[0][0] == depth + 1:
                    first = inner.pop(0)
                    out.append((depth, marker, first[2]))
                out.extend(inner)
        elif kind == "table":  # [Worklog 통합] 표는 행 단위 "칸 | 칸" 한 줄로 (구조가 AI 입력에 남도록)
            for row in node.get("content", []) or []:
                cells = [" / ".join(text for _d, _m, text in _blocks(cell.get("content", []) or [])) for cell in row.get("content", []) or []]
                if any(cells):
                    out.append((depth, None, "| " + " | ".join(cells) + " |"))
        elif kind == "gantt":  # [Worklog 통합] 간트 막대는 "[간트] 이름 (MM/DD~MM/DD, 진행 n%)"
            for item in (node.get("attrs") or {}).get("items") or []:
                if isinstance(item, dict) and item.get("label"):
                    pct = item.get("progressPercent")
                    extra = f", 진행 {pct}%" if isinstance(pct, (int, float)) else ""
                    out.append((depth, None, f"[간트] {item['label']} ({_period(item.get('startDate'), item.get('endDate'))}{extra})"))
        elif kind in ("paragraph", "heading", "codeBlock"):
            for line in _inline(node).split("\n"):
                if line.strip():
                    out.append((depth, None, line.strip()))
        elif kind in ("blockquote", "listItem", "doc"):
            out.extend(_blocks(node.get("content", []), depth))
        elif node.get("content"):
            out.extend(_blocks(node["content"], depth))
    return out


def _doc(value: Any) -> dict[str, Any] | None:
    """{"format": "tiptap-json", "doc": {...}} / doc 자체 / None 모두 받는다."""
    if isinstance(value, dict) and isinstance(value.get("doc"), dict):
        return value["doc"]
    if isinstance(value, dict) and value.get("type") == "doc":
        return value
    return None


def tiptap_lines(value: Any) -> list[str]:
    """여러 줄 텍스트: 글머리 "- ", 번호 "1. ", 하위 목록은 두 칸 들여쓰기. 빈 문단은 버린다."""
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    doc = _doc(value)
    if doc is None:
        return []
    lines = []
    for depth, marker, text in _blocks(doc.get("content", [])):
        indent = "  " * depth  # 목록 항목은 그 목록의 깊이, 항목 안 이어지는 문단·하위 목록은 한 단계 더
        lines.append(f"{indent}{marker + ' ' if marker else ''}{text}")
    return lines


def tiptap_inline(value: Any) -> str:
    """한 줄로: 번호 목록은 ①②, 글머리 목록·문단은 " / "로 잇는다 (배경·목적 칸용)."""
    if isinstance(value, str):
        return " / ".join(tiptap_lines(value))
    doc = _doc(value)
    if doc is None:
        return ""
    parts = []
    for depth, marker, text in _blocks(doc.get("content", [])):
        if marker and marker[:-1].isdigit() and depth == 0 and int(marker[:-1]) <= len(CIRCLED):
            parts.append(f"{CIRCLED[int(marker[:-1]) - 1]} {text}")
        else:
            parts.append(text)
    joined = []
    for part in parts:
        if joined and part[:1] in CIRCLED and joined[-1][:1] in CIRCLED:
            joined[-1] += " " + part
        else:
            joined.append(part)
    return " / ".join(joined)


# ---------------------------------------------------------------- Task 에디터 섹션 (## 진행 현황 / ## 이슈 / ## 향후계획)
# [Worklog 통합] Task 하나 안에 MD처럼 "## 진행 현황 : …" 식으로 쓴 내용을 섹션별 contents{}로 나눈다 (결정 I38).
# 받는 형식: dict {"진행 현황": "..."|[...]} / MD 문자열 / tiptap 문서(heading 노드 또는 "## "로 시작하는 문단).

SECTION_PROGRESS, SECTION_ISSUE, SECTION_PLAN, SECTION_BODY = "진행 현황", "이슈", "향후계획", "내용"
SECTION_ORDER = (SECTION_PROGRESS, SECTION_ISSUE, SECTION_PLAN)
_SECTION_ALIASES = {
    SECTION_PROGRESS: ("진행 현황", "진행현황", "진행 상황", "진행상황", "진행", "실적", "수행 내용", "수행내용", "금주 실적", "progress"),
    SECTION_ISSUE: ("이슈", "이슈 사항", "이슈사항", "문제", "문제점", "리스크", "issue", "issues"),
    SECTION_PLAN: ("향후계획", "향후 계획", "계획", "다음 계획", "차주 계획", "추후 계획", "to-do", "todo", "next", "plan"),
}
_ALIAS = {re.sub(r"\s+", "", a).lower(): name for name, aliases in _SECTION_ALIASES.items() for a in aliases}
_HEADING_RE = re.compile(r"^\s*#{1,6}(\s*)([^:：]+?)\s*(?:[:：]\s*(.*))?$")


def section_name(raw: str) -> str:
    """섹션 이름 정규화: 별칭은 진행 현황 / 이슈 / 향후계획으로, 그 밖은 원래 이름."""
    text = raw.strip().strip("[]【】").strip()
    return _ALIAS.get(re.sub(r"\s+", "", text).lower(), text)


def _section_lines(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = SECTION_BODY
    for line in lines:
        match = _HEADING_RE.match(line)
        # "##이슈"처럼 붙여 쓴 것은 알려진 섹션 이름일 때만 제목으로 본다 ("#1 개선" 같은 본문 보호)
        if match and (match.group(1) or section_name(match.group(2)) in SECTION_ORDER):
            current = section_name(match.group(2))
            sections.setdefault(current, [])
            if match.group(3) and match.group(3).strip():
                sections[current].append(match.group(3).strip())
            continue
        if line.strip():
            sections.setdefault(current, []).append(line.rstrip())
    return {k: v for k, v in sections.items() if v}


def _tiptap_section_lines(doc: dict[str, Any]) -> list[str]:
    """tiptap → 줄 목록. heading 노드는 "## 제목" 줄로 바꿔 MD와 같은 규칙으로 나눈다."""
    lines: list[str] = []
    for node in doc.get("content", []) or []:
        if node.get("type") == "heading":
            lines.append("## " + _inline(node).replace("\n", " ").strip())
        else:
            lines += tiptap_lines({"type": "doc", "content": [node]})
    return lines


def task_sections(value: Any) -> dict[str, list[str]]:
    """Task 내용 → {섹션: [줄, ...]}. 섹션 표시가 없으면 {"내용": [...]}."""
    if isinstance(value, dict) and _doc(value) is None:
        out: dict[str, list[str]] = {}
        for raw, body in value.items():
            if isinstance(body, (list, tuple)):
                lines = [str(x).strip() for x in body if str(x).strip()]
            elif _doc(body) is not None:
                lines = tiptap_lines(body)
            else:
                lines = tiptap_lines(str(body)) if body is not None else []
            if lines:
                out.setdefault(section_name(str(raw)), []).extend(lines)
        return out
    if isinstance(value, str):
        return _section_lines(value.splitlines())
    doc = _doc(value)
    return _section_lines(_tiptap_section_lines(doc)) if doc is not None else {}


def task_contents(task: dict[str, Any]) -> dict[str, list[str]]:
    """Task의 섹션 내용: contents(동료 에디터가 쓸 수 있는 칸) → content 순으로 찾는다."""
    for field in ("contents", "content"):
        sections = task_sections(task.get(field))
        if sections:
            return sections
    return {}


def merge_contents(parts: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    """여러 Task의 섹션을 합친다. 순서: 진행 현황 → 이슈 → 향후계획 → 그 밖 → 내용."""
    merged: dict[str, list[str]] = {}
    for part in parts:
        for name, lines in part.items():
            merged.setdefault(name, []).extend(lines)
    rank = {name: i for i, name in enumerate(SECTION_ORDER)}
    keys = sorted(merged, key=lambda k: (rank.get(k, len(rank) + (k == SECTION_BODY)),))
    return {k: merged[k] for k in keys}


# ---------------------------------------------------------------- 공통

def _check(export: dict[str, Any], file_type: str, mapping: dict[str, Any], notes: list[str]) -> None:
    if export.get("fileType") != file_type:
        raise WorklogError(f"fileType {export.get('fileType')!r} ≠ {file_type}")
    version = str(export.get("schemaVersion"))
    if version not in mapping.get("schema_versions", []):
        notes.append(f"알 수 없는 schemaVersion {version} (지원: {', '.join(mapping.get('schema_versions', []))}) → 같은 구조로 가정")


def _md(iso: str | None) -> str:
    return f"{iso[5:7]}/{iso[8:10]}" if iso else EMPTY


def _period(start: str | None, end: str | None) -> str:
    if start and end:
        return _md(end) if start == end else f"{_md(start)}~{_md(end)}"
    if end:
        return f"~{_md(end)}"
    return f"{_md(start)}~" if start else EMPTY


def _as_of(export: dict[str, Any]) -> date:
    return datetime.fromisoformat(export["generatedAt"]).date()


def person_key(person: dict[str, Any] | None) -> str:
    """기록 ID에 쓰는 작성자 키: 사번, 없으면 UUID 앞 8자리 (소문자·숫자만)."""
    if not person:
        return "unknown"
    number = str(person.get("employeeNumber") or "").strip()
    if number.isalnum():
        return number.lower()
    return "".join(ch for ch in str(person.get("id", "")).lower() if ch.isalnum())[:8] or "unknown"


# ---------------------------------------------------------------- 과제

def _milestone_status(raw: str | None, mapping: dict[str, Any], notes: list[str], name: str) -> str:
    table = mapping["milestone_status"]
    if raw not in table:
        notes.append(f"마일스톤 '{name}': 알 수 없는 상태 {raw!r} → {mapping['milestone_status_default']}")
        return mapping["milestone_status_default"]
    return table[raw]


def to_project(export: dict[str, Any], mapping: dict[str, Any], notes: list[str] | None = None) -> dict[str, Any]:
    notes = notes if notes is not None else []
    _check(export, PROJECT_TYPE, mapping, notes)
    p = export["project"]
    if p.get("deletedAt"):
        raise WorklogError(f"삭제된 과제: {p.get('name')} ({p['id']})")
    as_of = _as_of(export)
    team = p.get("team") or {}
    parent = team.get("parent") or {}
    owner = p.get("owner") or {}
    people: dict[str, dict[str, Any]] = {}
    for person in [owner, *(p.get("members") or [])]:
        if person.get("id"):
            entry = people.setdefault(person["id"], {"name": person.get("name") or person["id"], "title": None,
                                                     "employee_number": None, "team": None})
            entry["employee_number"] = person.get("employeeNumber") or entry["employee_number"]
            entry["team"] = person.get("teamName") or entry["team"]
    member_ids = [m["id"] for m in p.get("members") or [] if m.get("id")]
    if owner.get("id") and owner["id"] not in member_ids:
        member_ids.insert(0, owner["id"])

    raw_status = p.get("status")
    status = mapping["project_status"].get(raw_status)
    if status is None:
        status = mapping["project_status_default"]
        notes.append(f"과제 상태 {raw_status!r}를 대응표에서 찾지 못함 → {status}")

    milestones = []
    general = []
    alive = sorted((m for m in export.get("milestones") or [] if not m.get("deletedAt")), key=lambda m: (m.get("sortOrder", 0), m["name"]))
    for m in alive:
        if m.get("isGeneral"):
            general.append(m["name"])
            continue
        index = len(milestones) + 1
        state = _milestone_status(m.get("status"), mapping, notes, m["name"])
        plan = m.get("plannedEnd")
        if state not in ("완료", "취소") and plan and date.fromisoformat(plan) < as_of:
            state = "지연"  # 계획 종료일이 지났는데 끝나지 않음 (코드 판정, 기준일 = export 생성일)
            notes.append(f"마일스톤 '{m['name']}': 계획 종료 {_md(plan)} 경과·미완료 → 지연 ({as_of.isoformat()} 기준)")
        milestones.append({
            "milestone_id": f"M{index}", "parent_id": None, "stage_code": f"S{index}", "name": m["name"], "scope": "common",
            "scope_label": _period(m.get("plannedStart"), m.get("plannedEnd")), "baseline": m.get("baselineEnd"),
            "plan": plan, "plan_text": None, "actual": m.get("actualEnd"), "status": state, "note": None,
            "order": index, "source_id": m["id"]})
    if general:
        notes.append(f"일반 업무 마일스톤은 일정 표에서 제외: {', '.join(general)}")

    late = [m for m in milestones if m["status"] == "지연"]
    slipped = [m for m in milestones if m["baseline"] and m["plan"] and m["plan"] > m["baseline"] and m["status"] != "완료"]
    health = "판단 불가" if not milestones else "지연" if late else "주의" if slipped else "정상"

    end = p.get("endDate") or p.get("startDate")
    undated = end is None
    if undated:  # [Worklog 통합] 과제 기간 미입력: 일정 칸은 "미정", 계산용 날짜는 마일스톤 계획(없으면 기준일)으로 채운다
        plans = sorted(d for m in milestones for d in (m["plan"],) if d)
        end = plans[-1] if plans else as_of.isoformat()
        notes.append("과제 시작·종료일이 없어 일정 칸을 '미정'으로 표시")
    stamp = export["generatedAt"]
    project = {
        "meta": {"schema": "project", "schema_version": "0.1", "revision": max(1, int(p.get("revision") or 1)),
                 "created_at": stamp, "updated_at": stamp, "updated_by": person_key(owner)},
        "project_id": p["id"], "name": p["name"],
        "org": {"group": parent.get("name") or team.get("name") or EMPTY, "dept": parent.get("name") or EMPTY,
                "team": team.get("name") or EMPTY},
        "owner": owner.get("id") or EMPTY, "members": member_ids, "reporters": [owner["id"]] if owner.get("id") else [],
        "period": {"start": p.get("startDate") or min([end, *(m["plan"] for m in milestones if m["plan"])]), "target": end,
                   "target_text": "미정" if undated else f"'{int(end[2:4]):02d}.{int(end[5:7]):02d}"},
        "status": status, "health": health,
        "type": {"template_id": "WORKLOG", "template_version": 1},
        "target": [], "target_label": team.get("name") or None,
        "background": tiptap_inline(p.get("background")) or EMPTY,
        "purpose": tiptap_inline(p.get("purpose")) or EMPTY,
        "kpis": [], "milestones": milestones, "change_log": [], "retrospective": None,
        "people": people,
        "source": {"system": "worklog", "revision": export.get("sourceRevision"), "generated_at": stamp, "milestones_managed": True},
    }
    if export.get("kpis"):
        notes.append(f"KPI {len(export['kpis'])}건: WorkLog KPI 형식이 정해지지 않아 아직 변환하지 않음 (docs/WorkLog_연동.md 요청 사항)")
    if p.get("retrospective"):
        text = tiptap_inline(p["retrospective"])
        if text:
            project["retrospective"] = {"text": text, "source_ids": [p["id"]], "generated": False, "confirmed_by": None, "confirmed_at": None}
    return project


# ---------------------------------------------------------------- 업무일지

def _record_text(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    snap = record.get("originalSnapshot") or record
    return " / ".join(tiptap_lines(snap.get("content"))), snap


def _record_line(label: str, record: dict[str, Any], mapping: dict[str, Any]) -> str | None:
    text, snap = _record_text(record)
    if not text:
        return None
    attrs = []
    if snap.get("status"):
        attrs.append(f"상태 {mapping.get('record_status', {}).get(snap['status'], snap['status'])}")
    if snap.get("assigneeName"):
        attrs.append(f"담당 {snap['assigneeName']}")
    if snap.get("dueDate"):
        attrs.append(f"기한 {int(snap['dueDate'][5:7])}/{int(snap['dueDate'][8:10])}")
    for key, title in (("impact", "영향"), ("response", "대응")):
        value = snap.get(key)
        value = " / ".join(tiptap_lines(value)) if value else ""
        if value:
            attrs.append(f"{title} {value}")
    return f"[{label}] {text}" + (f" ({', '.join(attrs)})" if attrs else "")


def _achievement_line(item: Any, mapping: dict[str, Any]) -> str | None:
    if isinstance(item, str):
        return f"[성과] {item}" if item.strip() else None
    if isinstance(item, dict) and ("originalSnapshot" in item or "content" in item):
        return _record_line("성과", item, mapping)
    return None


def log_text(log: dict[str, Any], milestone_names: dict[str, str], mapping: dict[str, Any]) -> str:
    lines: list[str] = []
    for task in sorted(log.get("tasks") or [], key=lambda t: t.get("sortOrder", 0)):
        ref = task.get("milestone") or {}
        stage = milestone_names.get(ref.get("id")) or ref.get("nameSnapshot") or "마일스톤 없음"
        when = _period(task.get("performedStart"), task.get("performedEnd"))
        lines.append(f"[수행] ({stage}) {task.get('title') or '제목 없음'} ({when})")
        # [Worklog 통합] 섹션(## 진행 현황 / ## 이슈 / ## 향후계획)별 한 줄씩 — 표시 없는 내용은 기존처럼 줄 단위
        for name, body in merge_contents([task_contents(task)]).items():
            if name == SECTION_BODY:
                lines += [f"  {line}" for line in body]
            else:
                lines.append(f"  [{name}] " + " / ".join(line.strip() for line in body))
        if task.get("attachments"):
            lines.append(f"  (첨부 {len(task['attachments'])}건)")
    for key, label in (("achievements", None), ("issueRecords", "이슈"), ("todoRecords", "할 일")):
        for record in log.get(key) or []:
            line = _achievement_line(record, mapping) if label is None else _record_line(label, record, mapping)
            if line:
                lines.append(line)
    for key, label in (("lessonLearned", "배운 점"), ("note", "비고")):
        body = tiptap_lines(log.get(key))
        if body:
            lines.append(f"[{label}] " + " / ".join(body))
    people = [f"{c.get('name')}({c['team']})" if c.get("team") else str(c.get("name")) for c in log.get("collaborators") or [] if c.get("name")]
    if people:
        lines.append("[협업] " + ", ".join(people))
    return "\n".join(lines)


def to_dailies(export: dict[str, Any], project: dict[str, Any], mapping: dict[str, Any],
               notes: list[str] | None = None) -> list[dict[str, Any]]:
    notes = notes if notes is not None else []
    _check(export, DAILY_TYPE, mapping, notes)
    if (export.get("project") or {}).get("deletedAt"):
        return []
    day = date.fromisoformat(export["date"])
    milestone_names = {m["source_id"]: m["name"] for m in project.get("milestones", []) if m.get("source_id")}
    counters: dict[str, int] = {}
    dailies = []
    for log in sorted(export.get("logs") or [], key=lambda l: (person_key(l.get("author")), l.get("createdAt") or "", l.get("id") or "")):
        if log.get("deletedAt"):
            continue
        text = log_text(log, milestone_names, mapping)
        if not text:
            notes.append(f"{export['date']} {(log.get('author') or {}).get('name')}: 내용 없는 업무일지 건너뜀")
            continue
        key = person_key(log.get("author"))
        counters[key] = counters.get(key, 0) + 1
        daily_id = f"D-{day.strftime('%y%m%d')}-{key}-{counters[key]:02d}"
        refs: dict[str, Any] = {"log": log.get("id") or ""}
        refs["tasks"] = [t["id"] for t in log.get("tasks") or [] if t.get("id")]
        contents = merge_contents([task_contents(t) for t in sorted(log.get("tasks") or [], key=lambda t: t.get("sortOrder", 0))])
        refs["records"] = [r["refId"] for k in ("issueRecords", "todoRecords", "achievements") for r in log.get(k) or []
                           if isinstance(r, dict) and r.get("refId")]
        dailies.append({
            "meta": {"schema": "daily", "schema_version": "0.1", "revision": max(1, int(log.get("revision") or 1)),
                     "created_at": log.get("createdAt") or export["generatedAt"], "updated_at": log.get("updatedAt") or export["generatedAt"],
                     "updated_by": key},
            "daily_id": daily_id, "date": export["date"], "tag": day.strftime("%y-%m-%d"), "author": key,
            "author_name": (log.get("author") or {}).get("name"), "project_id": export["project"]["id"], "category": None,
            "visibility": "project", "raw_text": text, "tables": [], "pics": [], "links": [], "deleted": False, "source_refs": refs,
            "contents": contents,  # [Worklog 통합] Task 섹션 합본 (요약·PPT 입력)
        })
    return dailies


# ---------------------------------------------------------------- 마일스톤 snapshot (주차별 변경 표시)

SNAPSHOT_FIELDS = ("baseline", "plan", "actual", "status")


def is_managed(project: dict[str, Any]) -> bool:
    """일정·상태를 원본 시스템이 관리하는 과제인지 (WorkLog)."""
    return bool((project.get("source") or {}).get("milestones_managed"))


def milestone_snapshot(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["source_id"]: {"milestone_id": m["milestone_id"], "name": m["name"], **{f: m.get(f) for f in SNAPSHOT_FIELDS}}
            for m in project["milestones"] if m.get("source_id")}


def snapshot_changes(current: dict[str, dict[str, Any]], previous: dict[str, dict[str, Any]] | None) -> list[tuple[str, str, Any, Any]]:
    """(원본 마일스톤 ID, 필드, 이전 값, 이번 값). 지난주 snapshot이 없으면 비교하지 않는다(빈 목록)."""
    if not previous:
        return []
    changes = []
    for sid, now in current.items():
        before = previous.get(sid)
        if before is None:
            changes.append((sid, "status", None, now["status"]))  # 이번 주 새로 생긴 단계
            continue
        changes += [(sid, f, before.get(f), now.get(f)) for f in SNAPSHOT_FIELDS if before.get(f) != now.get(f)]
    return changes


def overlay_snapshot(project: dict[str, Any], snapshot: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """과거 주차 PPT를 만들 때: 그 주에 저장한 snapshot 값으로 일정·상태를 되돌린 복사본 (원본은 그대로)."""
    from copy import deepcopy

    result = deepcopy(project)
    for m in result["milestones"]:
        saved = (snapshot or {}).get(m.get("source_id"))
        if saved:
            m.update({f: saved.get(f) for f in SNAPSHOT_FIELDS})
    return result
