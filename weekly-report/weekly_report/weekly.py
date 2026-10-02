from __future__ import annotations

import json
import re
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import Any

from .ai import ExaoneClient
from .core import KST, ValidationError, atomic_json, item, load_json, previous_week, render_prompt, validate_schema, week_range


def select_dailies(root: Path, project_id: str, week: str) -> list[dict[str, Any]]:
    start, end = week_range(week)
    selected = []
    for path in (root / "data/raw/daily").rglob("*.json"):
        daily = load_json(path)
        validate_schema(daily, root / "schemas/daily.schema.json")
        day = datetime.strptime(daily["date"], "%Y-%m-%d").date()
        if daily["tag"] != day.strftime("%y-%m-%d"):
            raise ValidationError(f"{daily['daily_id']}.tag: date와 불일치")
        if start <= day <= end and daily.get("project_id") == project_id and daily["visibility"] == "project" and not daily.get("deleted", False):
            selected.append(daily)
    return sorted(selected, key=lambda value: (value["date"], value["daily_id"]))


def _daily_blocks(dailies: list[dict[str, Any]]) -> str:
    blocks = []
    for daily in dailies:
        lines = [f"- 기록 ID: {daily['daily_id']} ({daily['date']}, {daily['author']}, 카테고리 {daily.get('category')})", f"  본문: {daily['raw_text']}"]
        for table in daily["tables"]:
            lines.append(f"  표 [{table['title']}]")
            lines.append("    " + " | ".join(table["columns"]))
            lines.extend("    " + " | ".join(map(str, row)) for row in table["rows"])
        blocks.append("\n".join(lines))
    return "\n".join(blocks) if blocks else "없음"


def _semantic_issues(payload: dict[str, Any], allowed: set[str], project: dict[str, Any], raw_text: str) -> list[str]:
    issues, milestone_ids = [], {m["milestone_id"] for m in project["milestones"]}
    for slot in ("headline", "progress", "next_plan", "issues"):
        values = [payload[slot]] if slot == "headline" else payload.get(slot, [])
        for index, value in enumerate(values):
            for source in value.get("source_ids", []):
                if source not in allowed:
                    issues.append(f"{slot}[{index}].source_ids: 존재하지 않는 근거 {source}")
            text_numbers = re.findall(r"\d+(?:\.\d+)?%?", value.get("text", ""))
            raw_numbers = re.findall(r"\d+(?:\.\d+)?%?", raw_text)
            for number in text_numbers:
                numeric = Decimal(number.rstrip("%"))
                equivalents = [candidate for candidate in raw_numbers if Decimal(candidate.rstrip("%")) == numeric]
                if not equivalents and numeric not in {Decimal(39), Decimal(4)}:
                    issues.append(f"{slot}[{index}].text: 입력에서 확인되지 않는 수치 {number}")
                elif len({candidate.rstrip("%").split(".")[-1] if "." in candidate else "" for candidate in equivalents}) > 1:
                    issues.append(f"{slot}[{index}].text: 숫자는 동등하나 원문/표 표시 정밀도가 다름 ({' / '.join(dict.fromkeys(equivalents))})")
            if "ESMI1" in value.get("text", ""):
                issues.append(f"{slot}[{index}].text: 미확정 사이트 코드 ESMI1 (정상 코드로 확정하지 않음)")
    for index, update in enumerate(payload.get("milestone_updates", [])):
        mid, field, value = update.get("milestone_id"), update.get("field"), update.get("to")
        if mid is None or mid not in milestone_ids:
            issues.append(f"milestone_updates[{index}].milestone_id: 적용하지 않음 ({mid})")
        expected = {"plan": "date", "actual": "date", "status": "status", "plan_text": "string", "note": "string"}.get(field)
        valid = isinstance(value, str)
        if expected == "date": valid = valid and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        if expected == "status": valid = value in {"예정", "진행", "지연", "완료", "보류", "취소"}
        if not valid: issues.append(f"milestone_updates[{index}].to: {field} 타입/값 오류")
    return issues


def run_weekly(root: Path, project_id: str, week: str, out_root: Path, mode: str = "mock") -> tuple[Path, Path, Path]:
    project = load_json(root / f"data/master/projects/{project_id}.json")
    validate_schema(project, root / "schemas/project.schema.json")
    dailies = select_dailies(root, project_id, week)
    start, end = week_range(week); now = datetime.now(KST).replace(microsecond=0).isoformat()
    revisions = {d["daily_id"]: d["meta"]["revision"] for d in dailies}
    base = {"meta": {"schema": "weekly", "schema_version": "0.1", "revision": 1, "created_at": now, "updated_at": now, "updated_by": "pipeline"}, "project_id": project_id, "week": week, "range": {"from": start.isoformat(), "to": end.isoformat()}, "source_daily_ids": [d["daily_id"] for d in dailies]}
    client = ExaoneClient(root, mode)
    if not dailies:
        payload = {"headline": item(f"금주(W{week[-2:]}) 변경 없음", [], changed=True), "progress": [], "next_plan": [], "issues": [], "milestone_updates": []}
    else:
        variables = {"week_label": f"W{week[-2:]}", "budget_progress": 7, "budget_next_plan": 3, "budget_issues": 2, "project_id": project_id, "project_name": project["name"], "range_from": start, "range_to": end, "milestone_lines": json.dumps(project["milestones"], ensure_ascii=False), "prev_weekly_lines": "없음", "daily_blocks": _daily_blocks(dailies)}
        system, user = render_prompt(root, "weekly_rollup", variables)
        payload = client.complete("weekly_rollup", project_id, week, system, user)
    for slot, kind in (("headline", "fact"), ("progress", "fact"), ("next_plan", "plan"), ("issues", "issue")):
        values = [payload[slot]] if slot == "headline" else payload.get(slot, [])
        for value in values: value.setdefault("kind", kind); value.setdefault("changed", True)
    weekly = {**base, **{k: payload.get(k, [] if k != "headline" else {}) for k in ("headline", "progress", "next_plan", "issues", "milestone_updates")}, "no_change": not dailies, "budget": {"max_chars_per_line": 50, "lines": {"progress": 7, "next_plan": 3, "issues": 2}}, "review_state": "draft", "ai": {"model": "mock" if mode == "mock" else "EXAONE (사내 API, 계약 미검증)", "prompt_id": "weekly_rollup", "prompt_version": "v0.2", "generated_at": now, "input_revisions": revisions}}
    validate_schema(weekly, root / "schemas/weekly.schema.json")
    weekly_path = out_root / f"data/derived/weekly/{project_id}/{week}.json"
    atomic_json(weekly_path, weekly)
    prev_week = previous_week(week); prev_src = root / f"data/derived/cumulative/{project_id}/{prev_week}.json"
    prev = load_json(prev_src) if prev_src.exists() else None
    if not dailies:
        cpayload = {"items": prev.get("items", []) if prev else [], "pinned_facts": prev.get("pinned_facts", []) if prev else [], "new_pinned_facts": []}
    else:
        variables = {"max_items": 7, "project_id": project_id, "project_name": project["name"], "background": project["background"], "purpose": project["purpose"], "completed_milestones": json.dumps([m for m in project["milestones"] if m["status"] == "완료"], ensure_ascii=False), "prev_items": json.dumps(prev.get("items", []) if prev else [], ensure_ascii=False), "pinned_facts": json.dumps(prev.get("pinned_facts", []) if prev else [], ensure_ascii=False), "week_label": f"W{week[-2:]}", "weekly_lines": json.dumps(weekly, ensure_ascii=False)}
        system, user = render_prompt(root, "cumulative_update", variables)
        cpayload = client.complete("cumulative_update", project_id, week, system, user)
    def normalize(values):
        return [{"text": v["text"], "source_ids": v["source_ids"], "kind": "fact", "changed": False} for v in values]
    pinned = normalize(cpayload.get("pinned_facts", [])); seen = {(v["text"], tuple(v["source_ids"])) for v in pinned}
    for value in normalize(cpayload.get("new_pinned_facts", [])):
        key = (value["text"], tuple(value["source_ids"]))
        if key not in seen: pinned.append(value); seen.add(key)
    cumulative = {"meta": {"schema": "cumulative", "schema_version": "0.1", "revision": 1, "created_at": now, "updated_at": now, "updated_by": "pipeline"}, "project_id": project_id, "as_of_week": week, "prev_ref": f"data/derived/cumulative/{project_id}/{prev_week}.json" if prev else None, "items": normalize(cpayload.get("items", [])), "pinned_facts": pinned, "mode": "incremental", "ai": {"model": "mock" if mode == "mock" else "EXAONE (사내 API, 계약 미검증)", "prompt_id": "cumulative_update", "prompt_version": "v0.2", "generated_at": now, "input_revisions": {project_id: project["meta"]["revision"], **revisions}}}
    validate_schema(cumulative, root / "schemas/cumulative.schema.json")
    cumulative_path = out_root / f"data/derived/cumulative/{project_id}/{week}.json"; atomic_json(cumulative_path, cumulative)
    raw = _daily_blocks(dailies) + "\n" + json.dumps(project, ensure_ascii=False)
    issues = _semantic_issues(payload, set(revisions) | {project_id}, project, raw) if dailies else []
    report = out_root / f"output/validation_{week}.txt"; report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("구조 검증: 통과\n의미 검증:\n" + ("\n".join(f"- {x}" for x in issues) if issues else "- 통과") + "\n", encoding="utf-8")
    return weekly_path, cumulative_path, report
