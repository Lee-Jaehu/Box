"""WorkLog export(동료가 만든 업무기록 시스템의 JSON) → 내부 project/daily 형식 변환.

- WORKLOG_PROJECT_EXPORT  → 내부 project (schemas/project.schema.json)
- WORKLOG_DAILY_EXPORT    → 내부 daily 목록 (log 1건 = daily 1건, schemas/daily.schema.json)
원본 파일은 읽기만 한다. 값 대응은 config/worklog_mapping.json, 규칙 설명은 docs/WorkLog_연동.md.

결정 사항 (2026-10-04)
- 마일스톤 일정·상태는 WorkLog 값이 기준(milestones_managed). AI 일정 추출은 쓰지 않는다.
- WorkLog에 없는 칸: 주간 PPT '대상' = 팀명, 마일스톤 '적용 범위' = 계획 기간(MM/DD~MM/DD).
"""

from __future__ import annotations

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
    stamp = export["generatedAt"]
    project = {
        "meta": {"schema": "project", "schema_version": "0.1", "revision": max(1, int(p.get("revision") or 1)),
                 "created_at": stamp, "updated_at": stamp, "updated_by": person_key(owner)},
        "project_id": p["id"], "name": p["name"],
        "org": {"group": parent.get("name") or team.get("name") or EMPTY, "dept": parent.get("name") or EMPTY,
                "team": team.get("name") or EMPTY},
        "owner": owner.get("id") or EMPTY, "members": member_ids, "reporters": [owner["id"]] if owner.get("id") else [],
        "period": {"start": p.get("startDate") or end, "target": end,
                   "target_text": f"'{int(end[2:4]):02d}.{int(end[5:7]):02d}" if end else None},
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
        lines += [f"  {line}" for line in tiptap_lines(task.get("content"))]
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
        refs["records"] = [r["refId"] for k in ("issueRecords", "todoRecords", "achievements") for r in log.get(k) or []
                           if isinstance(r, dict) and r.get("refId")]
        dailies.append({
            "meta": {"schema": "daily", "schema_version": "0.1", "revision": max(1, int(log.get("revision") or 1)),
                     "created_at": log.get("createdAt") or export["generatedAt"], "updated_at": log.get("updatedAt") or export["generatedAt"],
                     "updated_by": key},
            "daily_id": daily_id, "date": export["date"], "tag": day.strftime("%y-%m-%d"), "author": key,
            "author_name": (log.get("author") or {}).get("name"), "project_id": export["project"]["id"], "category": None,
            "visibility": "project", "raw_text": text, "tables": [], "pics": [], "links": [], "deleted": False, "source_refs": refs,
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
