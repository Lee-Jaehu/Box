"""weekly: 해당 주 Daily 원문 → weekly JSON + cumulative JSON.

- AI 응답은 "내용 payload"로만 받는다. meta·project_id·week/range·no_change·review_state·ai·input_revisions는 코드가 채운다.
- changed는 지난주 정리본과의 비교(Rule)로 최종 판정한다. AI 값과 다르면 보고서에 남긴다.
- 고정 사실(pinned_facts)은 코드가 보존한다 (AI가 빠뜨리거나 바꿔도 이전 값 유지).
- 구조(스키마) 오류는 저장하지 않는다. 구조는 맞고 의미 검증에 실패한 항목은 저장하고 보고서에 표시한다.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import prompt_vars as pv
from .ai import ExaoneClient
from .codes import CodeTable
from .core import KST, ValidationError, atomic_json, load_json, previous_week, render_prompt, validate_schema, week_range
from .ppt.compose import norm_text
from .textmetrics import SENTENCE_MAX, sentence_problems
from . import sources
from .worklog import is_managed, milestone_snapshot, snapshot_changes
from .validate import Issue, build_evidence, id_dates, check_item, check_milestone_updates, sort_issues

ITEM_KEYS = ("text", "source_ids", "kind", "changed")
KINDS = {"fact", "judgement", "plan", "issue"}
SLOT_KIND = {"headline": "fact", "progress": "fact", "next_plan": "plan", "issues": "issue"}
BUDGET = {"progress": 7, "next_plan": 3, "issues": 2}
MAX_CUMULATIVE_ITEMS = 7
MAX_NEW_PINNED = 2


def iso_week(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def select_dailies(root: Path, project_id: str, week: str, warnings: list[str] | None = None,
                   project: dict[str, Any] | None = None, period: tuple[date, date] | None = None) -> list[dict[str, Any]]:
    """project_id 일치 + visibility=project + deleted가 아님 + Daily.date가 해당 ISO 주(월~일)인 것.

    내부 형식 Daily(data/raw/daily)와 WorkLog 업무일지(log 1건 = Daily 1건으로 변환)를 함께 고른다.
    [Worklog 통합] period를 주면 ISO 주 대신 그 기간(양 끝 포함)으로 고른다.
    """
    start, end = period or week_range(week)
    selected = []
    if project is None:
        project = sources.load_project(root, project_id, warnings)
    for daily in sources.worklog_dailies(root, project, warnings):
        if start <= date.fromisoformat(daily["date"]) <= end:
            selected.append(daily)
    for path in sorted((root / "data/raw/daily").rglob("*.json")):
        daily = load_json(path)
        relevant = isinstance(daily, dict) and daily.get("project_id") == project_id
        try:
            validate_schema(daily, root / "schemas/daily.schema.json")
            day = datetime.strptime(daily["date"], "%Y-%m-%d").date()
            if daily["tag"] != day.strftime("%y-%m-%d"):
                raise ValidationError(f"{daily['daily_id']}.tag: date와 불일치")
        except (ValidationError, ValueError, KeyError) as exc:
            if relevant:
                raise ValidationError(f"{path.name}: {exc}") from exc
            if warnings is not None:
                warnings.append(f"{path.name}: 다른 과제·형식 오류 Daily 건너뜀 ({exc})")
            continue
        if start <= day <= end and relevant and daily["visibility"] == "project" and daily.get("deleted") is not True:
            selected.append(daily)
    return sorted(selected, key=lambda value: (value["date"], value["daily_id"]))


def _find_derived(kind: str, project_id: str, week: str, out_root: Path, root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    for base in dict.fromkeys([out_root, root]):
        path = base / f"data/derived/{kind}/{project_id}/{week}.json"
        if path.exists():
            return path, load_json(path)
    return None, None


def _normalize_item(value: Any, path: str, notes: list[Issue], default_kind: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise ValidationError(f"{path}: 항목 형식 오류 (text 필요)")
    sources = value.get("source_ids", [])
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise ValidationError(f"{path}.source_ids: 문자열 배열이어야 함")
    extra = sorted(set(value) - set(ITEM_KEYS))
    if extra:
        notes.append(Issue(path, "정보", f"스키마에 없는 필드 제거: {', '.join(extra)}"))
    kind = value.get("kind") if value.get("kind") in KINDS else default_kind
    if value["text"].rstrip().endswith("(판단)"):
        kind = "judgement"
    item = {"text": value["text"].strip(), "source_ids": list(dict.fromkeys(sources)), "kind": kind}
    if isinstance(value.get("changed"), bool):
        item["changed"] = value["changed"]
    return item


def build_weekly_payload(payload: Any, notes: list[Issue]) -> dict[str, Any]:
    """AI payload → weekly 내용 필드 (구조 오류는 ValidationError)."""
    if not isinstance(payload, dict):
        raise ValidationError("weekly_rollup 응답이 JSON 객체가 아님")
    extra = sorted(set(payload) - {"headline", "progress", "next_plan", "issues", "milestone_updates"})
    if extra:
        notes.append(Issue("$", "정보", f"응답의 알 수 없는 필드 무시: {', '.join(extra)}"))
    content: dict[str, Any] = {"headline": _normalize_item(payload.get("headline"), "headline", notes, "fact")}
    for slot in ("progress", "next_plan", "issues"):
        values = payload.get(slot, [])
        if not isinstance(values, list):
            raise ValidationError(f"{slot}: 배열이어야 함")
        content[slot] = [_normalize_item(v, f"{slot}[{i}]", notes, SLOT_KIND[slot]) for i, v in enumerate(values)]
        if len(values) > BUDGET[slot]:
            notes.append(Issue(slot, "주의", f"항목 {len(values)}개 > 예산 {BUDGET[slot]}개 (PPT 생성 시 fit_to_budget/(계속) 처리)"))
    updates = payload.get("milestone_updates", [])
    if not isinstance(updates, list):
        raise ValidationError("milestone_updates: 배열이어야 함")
    content["milestone_updates"] = [
        {"milestone_id": u.get("milestone_id"), "field": u.get("field"), "to": u.get("to"),
         "reason": u.get("reason") if isinstance(u.get("reason"), str) else None,
         "source_ids": list(u.get("source_ids") or [])}
        for u in updates if isinstance(u, dict)
    ]
    return content


MILESTONE_POLICY = {
    "ai": "이번 주 메모에서 확인된 마일스톤 일정·상태 변화",
    "managed": "항상 []로 둔다. 일정·상태는 업무기록 시스템(WorkLog)이 관리하며 코드가 시스템 값을 그대로 쓴다",
}


def managed_updates(project: dict[str, Any], snapshot: dict[str, Any], prev_weekly: dict[str, Any] | None,
                    ai_updates: list[dict[str, Any]], notes: list[Issue]) -> list[dict[str, Any]]:
    """WorkLog 관리 과제: AI 일정 변화는 버리고, 지난주 snapshot 대비 바뀐 시스템 값만 변경으로 기록한다 (PPT 파란색)."""
    if ai_updates:
        notes.append(Issue("milestone_updates", "정보", f"WorkLog가 일정을 관리하는 과제 → AI가 낸 일정 변화 {len(ai_updates)}건 무시"))
    previous = (prev_weekly or {}).get("milestone_snapshot")
    if not previous:
        notes.append(Issue("milestone_updates", "정보", "지난주 마일스톤 snapshot 없음 → 이번 주는 변경 표시 없이 현재 값만 저장"))
        return []
    rev = (project.get("source") or {}).get("revision")
    updates = []
    for sid, fld, old, new in snapshot_changes(snapshot, previous):
        if fld == "baseline" or new is None:
            notes.append(Issue("milestone_updates", "정보", f"{snapshot[sid]['name']}.{fld}: {old or '-'} → {new or '-'} (표의 변경 표시 대상 아님)"))
            continue
        updates.append({"milestone_id": snapshot[sid]["milestone_id"], "field": fld, "to": new,
                        "reason": f"WorkLog rev {rev}: {old or '-'} → {new}", "source_ids": [project["project_id"]]})
    notes.append(Issue("milestone_updates", "정보", f"WorkLog 일정 변경 {len(updates)}건 (지난주 snapshot 대비)"))
    return updates


def apply_changed_rule(content: dict[str, Any], prev_weekly: dict[str, Any] | None, notes: list[Issue]) -> None:
    """지난주 정리본에 같은 문장이 있으면 changed=false, 아니면 true. headline은 항상 true."""
    prev = {norm_text(v["text"]) for slot in ("progress", "next_plan", "issues") for v in (prev_weekly or {}).get(slot, [])}
    if prev_weekly is None:
        notes.append(Issue("changed", "정보", "지난주 정리본 없음 → 모든 항목 changed=true"))
    content["headline"]["changed"] = True
    for slot in ("progress", "next_plan", "issues"):
        for index, item in enumerate(content[slot]):
            rule = norm_text(item["text"]) not in prev
            if "changed" in item and item["changed"] != rule:
                notes.append(Issue(f"{slot}[{index}].changed", "정보", f"AI 판정 {item['changed']} → 지난주 비교 결과 {rule}로 확정"))
            item["changed"] = rule


def _cum_item(value: dict[str, Any]) -> dict[str, Any]:
    return {"text": value["text"], "source_ids": list(value.get("source_ids", [])), "kind": value.get("kind", "fact") if value.get("kind") in KINDS else "fact", "changed": False}


def merge_pinned(prev: list[dict[str, Any]], payload_pinned: list[Any], new_pinned: list[Any], notes: list[Issue]) -> list[dict[str, Any]]:
    """이전 고정 사실은 그대로 보존하고, 새 고정 사실만 중복 없이 추가한다."""
    result = [_cum_item(v) for v in prev]
    keys = {norm_text(v["text"]) for v in result}
    returned = {norm_text(v["text"]) for v in payload_pinned if isinstance(v, dict) and isinstance(v.get("text"), str)}
    for value in prev:
        if norm_text(value["text"]) not in returned:
            notes.append(Issue("pinned_facts", "주의", f"AI 응답에서 빠진 이전 고정 사실을 코드가 보존: {value['text']}"))
    for index, value in enumerate(payload_pinned):
        if isinstance(value, dict) and isinstance(value.get("text"), str) and norm_text(value["text"]) not in keys:
            notes.append(Issue(f"pinned_facts[{index}]", "오류", f"이전에 없던 고정 사실이 pinned_facts로 반환됨(변경 의심) → 무시: {value['text']}"))
    if len(new_pinned) > MAX_NEW_PINNED:
        notes.append(Issue("new_pinned_facts", "주의", f"{len(new_pinned)}개 > 최대 {MAX_NEW_PINNED}개"))
    for index, value in enumerate(new_pinned):
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            raise ValidationError(f"new_pinned_facts[{index}]: 항목 형식 오류")
        key = norm_text(value["text"])
        if key in keys:
            continue
        result.append(_cum_item(value))
        keys.add(key)
    return result


def style_issues(path: str, value: dict[str, Any], *, need_date: bool) -> list[Issue]:
    """문장 규칙(40~60자, 경어체, 진행 날짜) 위반은 '주의'로 보고한다. 저장·PPT 생성은 막지 않는다."""
    return [Issue(f"{path}.text", "주의", f"문장 규칙: {problem}") for problem in sentence_problems(value["text"], need_date=need_date)]


def _short(path: Path | None, *bases: Path) -> str:
    """보고서용 경로: 실행 위치(out_root/root) 기준 상대 경로."""
    if path is None:
        return "없음"
    for base in bases:
        try:
            return str(path.resolve().relative_to(base.resolve()))
        except ValueError:
            continue
    return path.name


def _issue_lines(title: str, issues: list[Issue]) -> list[str]:
    lines = [f"[{title}]"]
    if not issues:
        return lines + ["- 통과"]
    counts = {level: sum(i.level == level for i in issues) for level in ("오류", "주의", "정보")}
    lines.append("- " + ", ".join(f"{k} {v}건" for k, v in counts.items()))
    return lines + [f"- {i.format()}" for i in sort_issues(issues)]


def run_weekly(root: Path, project_id: str, week: str, out_root: Path, mode: str = "mock",
               client: ExaoneClient | None = None, *, period: tuple[date, date] | None = None,
               response_key: str | None = None) -> tuple[Path, Path, Path]:
    """[Worklog 통합] period=(시작일, 종료일)이면 임의 기간을 한 번에 정리한다 (prompt: period_rollup).

    이때 week는 종료일이 속한 ISO 주차(스키마·파일 이름용), 비교 대상 '지난 정리본'은 시작일 직전 주차의 결과,
    AI 응답 이름은 response_key(기본 week)로 구분한다. 결과는 out_root에 저장하므로 주간 결과와 섞이지 않게
    호출하는 쪽이 기간 전용 out_root를 넘긴다.
    """
    client = client or ExaoneClient(root, mode)
    codes = CodeTable.load(root)
    skipped: list[str] = []
    project = sources.load_project(root, project_id, skipped)
    managed = is_managed(project)
    dailies = select_dailies(root, project_id, week, skipped, project, period)
    start, end = period or week_range(week)
    week_label = f"W{week[-2:]}" if period is None else f"{start.month}/{start.day}~{end.month}/{end.day}"
    rollup_id = "weekly_rollup" if period is None else "period_rollup"
    resp_key = response_key or week
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    version = pv.prompt_version(root)
    revisions = {d["daily_id"]: d["meta"]["revision"] for d in dailies}
    daily_ids = set(revisions)

    prev_week = previous_week(week if period is None else iso_week(start))
    prev_weekly_path, prev_weekly = _find_derived("weekly", project_id, prev_week, out_root, root)
    prev_cum_path, prev_cum = _find_derived("cumulative", project_id, prev_week, out_root, root)
    for label, value, schema in (("지난주 weekly", prev_weekly, "weekly"), ("지난주 cumulative", prev_cum, "cumulative")):
        if value is not None:
            validate_schema(value, root / f"schemas/{schema}.schema.json")

    weekly_notes: list[Issue] = []
    input_notes: list[str] = []
    cum_notes: list[Issue] = []
    # 이전 주 일정 변화를 누적한 마일스톤으로 프롬프트를 만든다 (기준정보 파일은 그대로)
    from .ppt.milestones import apply_history, load_prior_weeklies

    prior_weeklies = load_prior_weeklies(project_id, week, out_root, root)
    if managed:  # WorkLog: 일정·상태는 시스템 값이 이미 최신 (AI·이전 주 덧씌움 없음)
        current_project = project
    else:
        current_project, _, _ = apply_history(project, prior_weeklies, {"week": week, "milestone_updates": []})

    # ---------------------------------------------------------------- weekly
    if not dailies:
        empty = f"금주({week_label})에는 변경 사항이 없습니다" if period is None else f"해당 기간({week_label})에는 변경 사항이 없습니다"
        content = {"headline": {"text": empty, "source_ids": [], "kind": "fact", "changed": True},
                   "progress": [], "next_plan": [], "issues": [], "milestone_updates": []}
        weekly_ai_model = "AI 호출 없음 (Daily 없음)"
    else:
        variables = {"week_label": week_label, "budget_progress": BUDGET["progress"], "budget_next_plan": BUDGET["next_plan"],
                     "budget_issues": BUDGET["issues"], "project_id": project_id, "project_name": project["name"],
                     "range_from": start.isoformat(), "range_to": end.isoformat(),
                     "milestone_lines": pv.milestone_lines(current_project["milestones"], codes),
                     "milestone_policy": MILESTONE_POLICY["managed" if managed else "ai"],
                     "prev_weekly_lines": pv.prev_weekly_lines(prev_weekly),
                     # [Worklog 통합] 원문 예산(AI_INPUT_CHARS)을 넘으면 기록마다 균등하게 줄인다
                     "daily_blocks": pv.daily_blocks(dailies, getattr(client, "input_chars", None), input_notes)}
        system, user = render_prompt(root, rollup_id, variables)
        content = build_weekly_payload(client.complete(rollup_id, project_id, resp_key, system, user), weekly_notes)
        apply_changed_rule(content, prev_weekly, weekly_notes)
        weekly_notes += [Issue("입력", "정보", n) for n in input_notes]
        weekly_ai_model = client.model_label
    snapshot = None
    if managed:
        snapshot = milestone_snapshot(project)
        content["milestone_updates"] = managed_updates(project, snapshot, prev_weekly, content.get("milestone_updates", []), weekly_notes)

    weekly = {
        "meta": {"schema": "weekly", "schema_version": "0.1", "revision": 1, "created_at": now, "updated_at": now, "updated_by": "pipeline"},
        "project_id": project_id, "week": week, "range": {"from": start.isoformat(), "to": end.isoformat()},
        "source_daily_ids": [d["daily_id"] for d in dailies], **content, "no_change": not dailies,
        "budget": {"max_chars_per_line": int(SENTENCE_MAX), "lines": dict(BUDGET)}, "review_state": "draft",
        "ai": {"model": weekly_ai_model, "prompt_id": rollup_id, "prompt_version": version, "generated_at": now, "input_revisions": revisions},
    }
    if snapshot is not None:
        weekly["milestone_snapshot"] = snapshot
    validate_schema(weekly, root / "schemas/weekly.schema.json")  # 구조 오류면 여기서 중단 (저장하지 않음)

    # ---------------------------------------------------------------- cumulative
    prev_items = [_cum_item(v) for v in (prev_cum or {}).get("items", [])]
    prev_pinned = (prev_cum or {}).get("pinned_facts", [])
    if not dailies:
        items, pinned = prev_items, [_cum_item(v) for v in prev_pinned]
        cum_ai_model = "AI 호출 없음 (Daily 없음, 이전 누적 유지)"
    else:
        from .pptgen import estimate_cumulative_items

        max_items, budget_note = estimate_cumulative_items(root, project, prior_weeklies, weekly, MAX_CUMULATIVE_ITEMS)
        cum_notes.append(Issue("items", "정보", budget_note))
        variables = {"max_items": max_items, "project_id": project_id, "project_name": project["name"],
                     "background": project["background"], "purpose": project["purpose"],
                     "completed_milestones": pv.completed_milestones(apply_history(project, prior_weeklies, weekly)[0]["milestones"]),
                     "prev_items": pv.cumulative_lines(prev_items), "pinned_facts": pv.cumulative_lines(prev_pinned),
                     "week_label": week_label, "weekly_lines": pv.weekly_lines(weekly)}
        system, user = render_prompt(root, "cumulative_update", variables)
        cpayload = client.complete("cumulative_update", project_id, resp_key, system, user)
        if not isinstance(cpayload, dict) or not isinstance(cpayload.get("items"), list):
            raise ValidationError("cumulative_update 응답에 items 배열이 없음")
        items = []
        for index, value in enumerate(cpayload["items"]):
            items.append(_cum_item(_normalize_item(value, f"items[{index}]", cum_notes, "fact")))
        if len(items) > max_items:
            cum_notes.append(Issue("items", "주의", f"{len(items)}개 > 최대 {max_items}개 (PPT 생성 시 한도 초과분은 fit_to_budget/(계속) 처리)"))
        pinned = merge_pinned(prev_pinned, cpayload.get("pinned_facts", []) or [], cpayload.get("new_pinned_facts", []) or [], cum_notes)
        cum_ai_model = client.model_label

    cumulative = {
        "meta": {"schema": "cumulative", "schema_version": "0.1", "revision": 1, "created_at": now, "updated_at": now, "updated_by": "pipeline"},
        "project_id": project_id, "as_of_week": week,
        "prev_ref": f"data/derived/cumulative/{project_id}/{prev_week}.json" if prev_cum is not None else None,
        "items": items, "pinned_facts": pinned, "mode": "incremental",
        "ai": {"model": cum_ai_model, "prompt_id": "cumulative_update", "prompt_version": version, "generated_at": now,
               "input_revisions": {project_id: project["meta"]["revision"], **revisions}},
    }
    validate_schema(cumulative, root / "schemas/cumulative.schema.json")

    # ---------------------------------------------------------------- 의미 검증 (저장은 하고 보고서에 표시)
    prev_texts = [v["text"] for slot in ("headline",) for v in ([prev_weekly[slot]] if prev_weekly else [])]
    prev_texts += [v["text"] for slot in ("progress", "next_plan", "issues") for v in (prev_weekly or {}).get(slot, [])]
    prev_cum_texts = [v["text"] for v in prev_items + [_cum_item(p) for p in prev_pinned]]
    computed = [week_label, f"{start.month}/{start.day}", f"{end.month}/{end.day}"]
    if dailies:
        ev_week = build_evidence(dailies=dailies, project=project, prev_texts=prev_texts + prev_cum_texts, computed=computed + id_dates(daily_ids),
                                 allowed_ids=daily_ids | {project_id}, codes=codes, prev_level="주의")
        weekly_notes += check_item("headline", weekly["headline"], ev_week)
        weekly_notes += style_issues("headline", weekly["headline"], need_date=False)
        for slot in ("progress", "next_plan", "issues"):
            for index, value in enumerate(weekly[slot]):
                weekly_notes += check_item(f"{slot}[{index}]", value, ev_week)
                weekly_notes += style_issues(f"{slot}[{index}]", value, need_date=slot != "next_plan")
        if not managed:  # WorkLog 일정 변화는 코드가 시스템 값으로 만든 것 → 근거 검사 대상 아님
            weekly_notes += check_milestone_updates(weekly["milestone_updates"], project, ev_week)

        prev_ids = {s for v in prev_items + prev_pinned for s in v.get("source_ids", [])}
        ev_cum = build_evidence(dailies=dailies, project=project, prev_texts=prev_cum_texts, computed=computed + id_dates(daily_ids | prev_ids),
                                allowed_ids=daily_ids | {project_id} | prev_ids, codes=codes, prev_level="정보")
        for key in ("items", "pinned_facts"):
            for index, value in enumerate(cumulative[key]):
                cum_notes += check_item(f"{key}[{index}]", value, ev_cum)
        for index, value in enumerate(cumulative["items"]):  # 고정 사실은 지난 문장 그대로라 문체 검사 제외
            cum_notes += style_issues(f"items[{index}]", value, need_date=True)

    # 저장: 두 파일 모두 구조 검증을 통과한 뒤에만 쓴다
    weekly_path = out_root / f"data/derived/weekly/{project_id}/{week}.json"
    cumulative_path = out_root / f"data/derived/cumulative/{project_id}/{week}.json"
    atomic_json(weekly_path, weekly)
    atomic_json(cumulative_path, cumulative)

    report = out_root / f"output/{project_id}/validation_{resp_key}.txt"
    lines = [f"과제 {project_id} / {week if period is None else '기간'} ({start.isoformat()} ~ {end.isoformat()})",
             f"AI 모드: {client.mode} / 프롬프트 {version}",
             f"선택 Daily: {', '.join(revisions) or '없음 (AI 호출 생략, no_change=true)'}",
             f"지난주 weekly: {_short(prev_weekly_path, out_root, root)}", f"지난주 cumulative: {_short(prev_cum_path, out_root, root)}", "",
             "[구조 검증]", "- weekly·cumulative JSON Schema 통과 (저장 완료)", ""]
    lines += [f"- {s}" for s in skipped]
    lines += _issue_lines("의미 검증 – weekly", weekly_notes) + [""] + _issue_lines("의미 검증 – cumulative", cum_notes)
    lines += ["", "※ 출처 태그: 원문=이번 주 Daily·표, 기준정보=master, 이전요약=지난주 누적/정리본(원문 미확인), 계산값=코드 계산"]
    report.parent.mkdir(parents=True, exist_ok=True)
    tmp = report.with_name(f".{report.name}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(report)
    return weekly_path, cumulative_path, report


def _semantic_issues(payload: dict[str, Any], allowed: set[str], project: dict[str, Any], raw_text: str) -> list[str]:
    """하위 호환용: weekly payload 의미 검증 결과를 문자열 목록으로 돌려준다."""
    evidence = build_evidence(dailies=[{"raw_text": raw_text}], project=project, allowed_ids=set(allowed))
    issues: list[Issue] = []
    for slot in ("headline", "progress", "next_plan", "issues"):
        values = [payload[slot]] if slot == "headline" else payload.get(slot, [])
        for index, value in enumerate(values):
            issues += check_item(slot if slot == "headline" else f"{slot}[{index}]", value, evidence)
    issues += check_milestone_updates(payload.get("milestone_updates", []), project, evidence)
    return [i.format() for i in sort_issues(issues)]
