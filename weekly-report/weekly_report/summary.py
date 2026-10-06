"""project_summary: 과제 1건 → 팀 요약 페이지용 요약 JSON (EXAONE이 문장, Rule이 순서·색·검증).

- 입력: 기준정보(배경·목적·마일스톤) + 누적 요약(기존) + 이번 주 weekly + 이번 주 업무 기록 원문 + 줄 수 한도
- 출력: data/derived/summary/{project_id}/{week}.json, 검증 보고서 output/{project_id}/summary_check_{week}.txt
- 신규(파랑) 여부는 AI가 정하지 않는다. source_ids에 이번 주 기록 ID가 있으면 신규, 배경은 항상 기존(검정).
- 구조 오류는 저장하지 않고, 의미 검증(수치·날짜·근거·문체) 실패는 저장한 뒤 보고서에 표시한다 (weekly와 같은 방식).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import prompt_vars as pv
from .ai import ExaoneClient, strip_source_tags
from .codes import CodeTable
from .core import KST, ValidationError, atomic_json, load_json, previous_week, render_prompt, validate_schema, week_range
from .textmetrics import has_date_note, is_polite, line_count, weighted_length
from .validate import Issue, build_evidence, check_item, id_dates, sort_issues

PROMPT_ID = "project_summary"
CATEGORIES = ("background", "progress", "issue", "good", "plan")
# 표시 순서: 배경 → 진행 → 이슈·잘한점(AI가 쓴 순서 유지) → 계획
CATEGORY_RANK = {"background": 0, "progress": 1, "issue": 2, "good": 2, "plan": 3}
CATEGORY_LABEL = {"background": "배경/목적", "progress": "진행 현황", "issue": "이슈", "good": "잘한점", "plan": "향후 계획"}
NEED_DATE = {"progress", "issue", "good"}
ITEM_CHARS = (40.0, 100.0)  # 항목: PPT 최대 2줄
DETAIL_CHARS = (20.0, 70.0)  # 세부: PPT 1줄
ITEM_PREFIX, DETAIL_PREFIX = "- ", "  . "


@dataclass
class SummaryResult:
    path: Path
    check: Path
    summary: dict[str, Any]
    issues: list[Issue]
    reused: bool = False


def item_lines(item: dict[str, Any], line_chars: float) -> int:
    """요약 페이지에서 이 항목이 차지하는 줄 수 (항목 + 세부)."""
    lines = line_count(ITEM_PREFIX + item["text"], line_chars)
    return lines + sum(line_count(DETAIL_PREFIX + d["text"], line_chars) for d in item.get("details", []))


def summary_lines(summary: dict[str, Any], line_chars: float) -> int:
    return sum(item_lines(item, line_chars) for item in summary["items"])


def text_problems(text: str, category: str, *, detail: bool) -> list[str]:
    """요약 페이지 문장 규칙 (항목 40~100자·세부 20~70자, 경어체, 진행·이슈·잘한점 항목은 끝에 날짜)."""
    low, high = DETAIL_CHARS if detail else ITEM_CHARS
    problems = []
    length = weighted_length(text)
    if length < low:
        problems.append(f"{length:.1f}자 < 최소 {low:g}자")
    elif length > high:
        problems.append(f"{length:.1f}자 > 최대 {high:g}자")
    if not is_polite(text):
        problems.append('경어체 종결("~했습니다/~입니다") 아님')
    if not detail and category in NEED_DATE and not has_date_note(text):
        problems.append('문장 끝 진행 날짜 "(M/D)" 없음')
    if category == "background" and has_date_note(text):
        problems.append("배경에는 날짜를 붙이지 않음")
    return problems


def _clean(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise ValidationError(f"{path}: 항목 형식 오류 (text 필요)")
    value = strip_source_tags(value)
    sources = value.get("source_ids", [])
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise ValidationError(f"{path}.source_ids: 문자열 배열이어야 함")
    return {"text": value["text"].strip(), "source_ids": list(dict.fromkeys(sources))}


def build_items(payload: dict[str, Any], project: dict[str, Any], week_ids: set[str], notes: list[Issue]) -> list[dict[str, Any]]:
    """AI 응답 → 저장 형식. 카테고리 확인, 순서 정렬, 신규(파랑) 판정은 Rule."""
    items = []
    for index, raw in enumerate(payload.get("items", [])):
        path = f"items[{index}]"
        category = raw.get("category") if isinstance(raw, dict) else None
        if category not in CATEGORIES:
            notes.append(Issue(path, "오류", f"알 수 없는 카테고리 {category!r} → 제외"))
            continue
        item = _clean(raw, path)
        details = raw.get("details") or []
        if not isinstance(details, list):
            raise ValidationError(f"{path}.details: 배열이어야 함")
        item["details"] = [_clean(d if isinstance(d, dict) else {"text": d, "source_ids": []}, f"{path}.details[{i}]")
                           for i, d in enumerate(details)]
        item["category"] = category
        items.append(item)
    if not any(i["category"] == "background" for i in items):
        # 배경이 빠지면 기준정보 문장으로 채운다 (기준정보 원문 그대로라 근거 = 과제 ID)
        text = " ".join(t.strip() for t in (project.get("background"), project.get("purpose")) if t and t.strip())
        items.insert(0, {"category": "background", "text": text, "source_ids": [project["project_id"]], "details": []})
        notes.append(Issue("items", "주의", "AI 응답에 배경(background)이 없어 기준정보 배경·목적 문장으로 채움"))
    items.sort(key=lambda i: CATEGORY_RANK[i["category"]])  # 같은 순위 안에서는 AI 순서 유지 (stable)
    for index, item in enumerate(items):
        new = item["category"] != "background" and bool(week_ids & set(item["source_ids"]))
        old = set(item["source_ids"]) - week_ids - {project["project_id"]}
        if new and old:
            notes.append(Issue(f"items[{index}]", "정보", "이번 주 기록과 이전 기록을 함께 근거로 씀 → 신규(파랑)로 표시"))
        for detail in item["details"]:
            detail["new"] = item["category"] != "background" and bool(week_ids & set(detail["source_ids"]) or (new and not detail["source_ids"]))
        ordered = {"category": item["category"], "text": item["text"], "source_ids": item["source_ids"], "new": new,
                   "details": item["details"]}
        items[index] = ordered
    return items


def _derived(kind: str, project_id: str, week: str, out_root: Path, root: Path, *, required: bool = True) -> dict[str, Any] | None:
    for base in dict.fromkeys([out_root, root]):
        path = base / f"data/derived/{kind}/{project_id}/{week}.json"
        if path.exists():
            return load_json(path)
    if not required:
        return None
    raise FileNotFoundError(f"{kind} 입력 없음: data/derived/{kind}/{project_id}/{week}.json (먼저 weekly를 실행하세요)")


def summary_path(out_root: Path, project_id: str, week: str) -> Path:
    return out_root / f"data/derived/summary/{project_id}/{week}.json"


def run_summary(root: Path, project: dict[str, Any], week: str, out_root: Path, *, client: ExaoneClient,
                max_lines: int, line_chars: float, dailies: list[dict[str, Any]] | None = None,
                current_project: dict[str, Any] | None = None) -> SummaryResult:
    """과제 1건 요약을 만들고 저장한다. 프롬프트 입력이 지난번과 같고 live 모드면 저장된 결과를 다시 쓴다.

    current_project: 이번 주 일정 변화를 덧씌운 기준정보(마일스톤 표시용). 없으면 project.
    """
    from .weekly import select_dailies

    pid = project["project_id"]
    weekly = _derived("weekly", pid, week, out_root, root)
    cumulative = _derived("cumulative", pid, week, out_root, root)
    # "기존" = 지난주까지의 누적 요약 (이번 주 누적 요약에는 이번 주 내용이 이미 합쳐져 있다)
    prev_cum = _derived("cumulative", pid, previous_week(week), out_root, root, required=False) or {"items": [], "pinned_facts": []}
    warnings: list[str] = []
    if dailies is None:
        dailies = select_dailies(root, pid, week, warnings, project)
    start, end = week_range(week)
    week_ids = {d["daily_id"] for d in dailies} | set(weekly.get("source_daily_ids", []))
    codes = CodeTable.load(root)
    variables = {"project_id": pid, "project_name": project["name"], "background": project["background"],
                 "purpose": project["purpose"], "max_lines": max_lines, "line_chars": int(line_chars),
                 "milestone_lines": pv.milestone_lines((current_project or project)["milestones"], codes),
                 "cumulative_lines": pv.cumulative_lines(prev_cum.get("items", [])),
                 "week_label": f"W{week[-2:]}", "range_from": start.isoformat(), "range_to": end.isoformat(),
                 "weekly_lines": _weekly_lines(weekly), "daily_blocks": pv.daily_blocks(dailies)}
    system, user = render_prompt(root, PROMPT_ID, variables)
    input_hash = hashlib.sha256(f"{system}\n{user}".encode("utf-8")).hexdigest()[:16]

    path = summary_path(out_root, pid, week)
    check = out_root / f"output/{pid}/summary_check_{week}.txt"
    if client.mode == "live" and path.exists():
        saved = load_json(path)
        if saved.get("ai", {}).get("input_hash") == input_hash:
            return SummaryResult(path, check, saved, [], reused=True)

    notes: list[Issue] = [Issue("입력", "정보", w) for w in warnings]
    payload = client.complete(PROMPT_ID, pid, week, system, user)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValidationError("project_summary 응답에 items 배열이 없음")
    items = build_items(payload, project, week_ids, notes)
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    revisions = {pid: project["meta"]["revision"], **{d["daily_id"]: d["meta"]["revision"] for d in dailies}}
    summary = {
        "meta": {"schema": "project_summary", "schema_version": "0.1", "revision": 1, "created_at": now, "updated_at": now,
                 "updated_by": "pipeline"},
        "project_id": pid, "week": week, "project_name": project["name"], "max_lines": max_lines,
        "week_source_ids": sorted(week_ids), "items": items,
        "ai": {"model": client.model_label, "prompt_id": PROMPT_ID, "prompt_version": pv.prompt_version(root),
               "generated_at": now, "input_revisions": revisions, "input_hash": input_hash},
    }
    validate_schema(summary, root / "schemas/project_summary.schema.json")  # 구조 오류면 저장하지 않음

    # 의미 검증: 수치·날짜·근거 ID (원문 → 기준정보 → 계산값 → 이전 요약 순)
    old_values = [v for c in (prev_cum, cumulative) for key in ("items", "pinned_facts") for v in c.get(key, [])]
    prev_texts = [v["text"] for v in old_values]
    prev_texts += [v["text"] for slot in ("progress", "next_plan", "issues") for v in weekly.get(slot, [])]
    old_ids = {s for v in old_values for s in v.get("source_ids", [])}
    old_ids |= {s for slot in ("progress", "next_plan", "issues") for v in weekly.get(slot, []) for s in v.get("source_ids", [])}
    allowed = week_ids | old_ids | {pid}
    evidence = build_evidence(dailies=dailies, project=project, prev_texts=prev_texts,
                              computed=[f"W{week[-2:]}", *id_dates(allowed)], allowed_ids=allowed, codes=codes, prev_level="정보")
    for index, item in enumerate(items):
        path_ = f"items[{index}]({CATEGORY_LABEL[item['category']]})"
        notes += check_item(path_, item, evidence, require_sources=item["category"] != "background")
        notes += [Issue(f"{path_}.text", "주의", f"문장 규칙: {p}") for p in text_problems(item["text"], item["category"], detail=False)]
        for d_index, detail in enumerate(item["details"]):
            notes += check_item(f"{path_}.details[{d_index}]", detail, evidence, require_sources=False)
            notes += [Issue(f"{path_}.details[{d_index}].text", "주의", f"문장 규칙: {p}")
                      for p in text_problems(detail["text"], item["category"], detail=True)]
    used = summary_lines(summary, line_chars)
    if used > max_lines:
        notes.append(Issue("items", "주의", f"예상 {used}줄 > 한도 {max_lines}줄 (요약 페이지에서 글자 크기를 줄이거나 다음 장으로 넘김)"))
    else:
        notes.append(Issue("items", "정보", f"예상 {used}줄 / 한도 {max_lines}줄 (한 줄 약 {int(line_chars)}자)"))

    atomic_json(path, summary)
    _write_check(check, summary, notes, client, used)
    return SummaryResult(path, check, summary, notes)


def _weekly_lines(weekly: dict[str, Any]) -> str:
    """요약 입력: 이번 주 진행·계획·이슈 (계획까지 준다)."""
    parts = [pv.item_lines(weekly.get(slot, []), with_slot=slot) for slot in ("progress", "next_plan", "issues")]
    return "\n".join(p for p in parts if p) or "없음 (이번 주 기록 없음)"


def _write_check(path: Path, summary: dict[str, Any], notes: list[Issue], client: ExaoneClient, used: int) -> None:
    lines = [f"과제 요약 {summary['project_id']} / {summary['week']} ({summary['project_name']})",
             f"AI 모드: {client.mode} / 프롬프트 {summary['ai']['prompt_version']} / 한도 {summary['max_lines']}줄, 예상 {used}줄",
             f"이번 주 기록(신규 판정 기준): {', '.join(summary['week_source_ids']) or '없음'}", "",
             "[요약 내용] (■ = 신규·파랑, □ = 기존·검정)"]
    for item in summary["items"]:
        mark = "■" if item["new"] else "□"
        lines.append(f"{mark} [{CATEGORY_LABEL[item['category']]}] {item['text']}")
        lines += [f"    {'■' if d['new'] else '□'} . {d['text']}" for d in item["details"]]
    lines += ["", "[구조 검증]", "- project_summary JSON Schema 통과 (저장 완료)", ""]
    lines.append("[의미 검증]")
    counts = {level: sum(i.level == level for i in notes) for level in ("오류", "주의", "정보")}
    lines.append("- " + ", ".join(f"{k} {v}건" for k, v in counts.items()))
    lines += [f"- {i.format()}" for i in sort_issues(notes)]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)
