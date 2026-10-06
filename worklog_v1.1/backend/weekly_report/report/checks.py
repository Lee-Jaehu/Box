"""보고 자료 AI 응답 검사와 칸 단위 대체.

검사 순서 (docs/보고자료_양식_분석.md 5.3)
1. JSON Schema (schemas/report_*.schema.json): 구조가 틀린 칸은 대체
2. 수치·날짜·근거 ID: validate.check_item. 근거 = 이번에 AI에 보낸 입력(user 프롬프트) + 기준정보
3. 분량·문체·강조 구절: report_vars.report_style_problems

오류가 있는 칸만 Rule 문장으로 바꾸거나(단일 칸) 그 항목을 뺀다(목록 칸). 무엇을 바꿨는지는 notes에 남긴다.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..core import load_json
from ..report_vars import EXEC_BUDGET, MONTHLY_BUDGET, REPORT_SLOTS, report_style_problems
from ..validate import RECORD_ID_RE, build_evidence, check_item

LIST_SLOTS = {"project_comments", "highlights", "risks", "requests", "left_items", "right_items"}


def prompt_evidence(user_prompt: str, projects: list[dict[str, Any]], computed: list[str] = ()):
    """AI에 보낸 입력 전체를 근거로 쓴다 (입력에 없는 수치·날짜·ID = 오류). computed = 코드가 아는 값(월, 과제 수)."""
    ids = set(RECORD_ID_RE.findall(user_prompt)) | {p["project_id"] for p in projects}
    merged = {"projects": projects}
    return build_evidence(dailies=[], project=merged, prev_texts=[user_prompt], computed=list(computed),
                          allowed_ids=ids, prev_level="정보")


def _items(value: Any) -> list[dict[str, Any]]:
    return [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, dict)]


def check_report(kind: str, payload: Any, root: Path, user_prompt: str, projects: list[dict[str, Any]],
                 fallback: dict[str, Any], computed: list[str] = ()) -> tuple[dict[str, Any], list[str]]:
    """검사 후 쓸 수 있는 payload와 처리 기록을 돌려준다. fallback = 칸별 Rule 대체값."""
    notes: list[str] = []
    schema = load_json(root / f"schemas/{kind}.schema.json")
    result = deepcopy(payload) if isinstance(payload, dict) else {}
    # 1) 구조: 틀린 최상위 칸은 대체
    bad_slots = set()
    for error in Draft202012Validator(schema).iter_errors(result):
        slot = error.absolute_path[0] if error.absolute_path else None
        if slot is None:  # 필수 칸 누락·알 수 없는 칸
            missing = re.findall(r"'([a-z_]+)' is a required property", error.message)
            extra = re.findall(r"'([a-z_]+)' (?:was|were) unexpected", error.message)
            bad_slots.update(missing)
            for key in extra:
                result.pop(key, None)
                notes.append(f"[정보] 알 수 없는 칸 무시: {key}")
        else:
            bad_slots.add(str(slot))
    for slot in sorted(bad_slots):
        notes.append(f"[대체] {slot}: 형식 오류 → Rule 값으로 대체")
        result[slot] = deepcopy(fallback[slot])
    # 2) 수치·날짜·근거
    evidence = prompt_evidence(user_prompt, projects, computed)
    for slot in REPORT_SLOTS[kind]:
        if slot in bad_slots:
            continue
        kept = []
        for index, item in enumerate(_items(result.get(slot))):
            errors = [i for i in check_item(slot, item, evidence) if i.level == "오류"]
            if errors:
                notes += [f"[대체] {slot}[{index}]: {e.message}" for e in errors]
            else:
                kept.append(item)
        if slot in LIST_SLOTS:
            result[slot] = kept
        elif len(kept) != len(_items(result.get(slot))):
            result[slot] = deepcopy(fallback[slot])
            notes.append(f"[대체] {slot}: 입력 근거 오류 → Rule 값으로 대체")
    # 3) 분량·문체·강조
    for problem in report_style_problems(kind, result):
        slot = problem.split(":")[0].split("[")[0]
        if slot == "emphasis":
            phrase = re.search(r"'(.+)'", problem).group(1)
            result["emphasis"] = [p for p in result.get("emphasis", []) if p != phrase]
            notes.append(f"[대체] {problem} → 강조 제외")
            continue
        index = re.search(r"\[(\d+)\]", problem.split(":")[0])
        if slot in LIST_SLOTS and index:
            notes.append(f"[대체] {problem} → 항목 제외")
            result[slot][int(index.group(1))] = None
        elif slot in fallback:
            notes.append(f"[대체] {problem} → Rule 값으로 대체")
            result[slot] = deepcopy(fallback[slot])
    for slot in LIST_SLOTS & set(result):
        result[slot] = [v for v in result[slot] if v is not None]
    # 월간: 과제마다 코멘트 1개 (없거나 모르는 과제면 Rule 대체)
    if kind == "report_monthly":
        given = {c["project_id"]: c for c in result.get("project_comments", [])}
        unknown = sorted(set(given) - {p["project_id"] for p in projects})
        if unknown:
            notes.append(f"[정보] 목록에 없는 과제 코멘트 무시: {', '.join(unknown)}")
        comments = []
        for project in projects:
            pid = project["project_id"]
            if pid in given:
                comments.append(given[pid])
            else:
                notes.append(f"[대체] project_comments: {pid} 코멘트 없음 → Rule 값")
                comments.append(next(c for c in fallback["project_comments"] if c["project_id"] == pid))
        result["project_comments"] = comments
    return result, notes or ["대체 없음 (AI 응답 그대로 사용)"]


def budget(kind: str) -> dict[str, int]:
    return MONTHLY_BUDGET if kind == "report_monthly" else EXEC_BUDGET
