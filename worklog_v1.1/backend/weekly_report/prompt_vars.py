"""prompts/README.md에 정의된 형식대로 프롬프트 변수 문자열을 만든다 (프롬프트 원문은 코드에 두지 않는다)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .codes import CodeTable

SLOT_LABEL = {"progress": "진행", "next_plan": "계획", "issues": "이슈", "headline": "요약"}


def prompt_version(root: Path) -> str:
    """prompts/README.md 제목의 버전(예: v0.2)을 읽는다."""
    head = (root / "prompts/README.md").read_text(encoding="utf-8").splitlines()[0]
    match = re.search(r"v\d+\.\d+", head)
    return match.group(0) if match else "unknown"


def milestone_lines(milestones: list[dict[str, Any]], codes: CodeTable) -> str:
    lines = []
    for m in sorted(milestones, key=lambda x: x["order"]):
        plan = m.get("plan_text") or m.get("plan") or "-"
        # WorkLog 단계는 적용 범위 대신 계획 기간, 실적일도 함께 준다
        scope = f"계획 기간: {m['scope_label']}" if m.get("source_id") else f"적용 범위: {codes.scope_label(m['scope'])}"
        actual = f" | 실적 {m['actual']}" if m.get("actual") else ""
        lines.append(
            f"- {m['milestone_id']} | {m['name']} | {scope} | "
            f"Baseline {m.get('baseline') or '-'} | 계획 {plan}{actual} | 상태 {m['status']}"
        )
    return "\n".join(lines) if lines else "없음"


# [Worklog 통합] 원문 예산: 넘으면 기록마다 균등하게(작은 기록은 그대로, 큰 기록부터) 줄인다. focus 표시 줄은 마지막까지 남긴다.
FOCUS_MARKS = ("[이슈]", "[성과]", "[배운 점]")
TRIM_MARK = "…(줄임)"


def _fill_caps(sizes: list[int], budget: int) -> list[int]:
    """물 채우기: 합이 budget 이하가 되는 기록별 상한 (작은 기록은 그대로)."""
    caps = list(sizes)
    if sum(sizes) <= budget:
        return caps
    order = sorted(range(len(sizes)), key=lambda i: sizes[i])
    left, remaining = max(budget, 0), len(sizes)
    for i in order:
        share = left // remaining
        caps[i] = min(sizes[i], share)
        left -= caps[i]
        remaining -= 1
    return caps


def _cut(lines: list[str], cap: int, free=lambda line: False) -> list[str]:
    """줄 목록을 약 cap 글자로 줄인다 (원래 순서 유지, 줄 단위, 넘치는 첫 줄은 글자 단위). free 줄은 세지 않고 남긴다."""
    out, used, full, cut = [], 0, False, False
    for line in lines:
        if free(line):
            out.append(line)
            continue
        if full:
            cut = True
            continue
        if used + len(line) + 9 <= cap:
            out.append(line)
            used += len(line) + 9
            continue
        room = cap - used - 9
        if room > 20:
            out.append(line[:room].rstrip() + "…")
        full = cut = True
    if cut:
        out.append(TRIM_MARK)
    return out


def _body_lines(daily: dict[str, Any]) -> list[str]:
    return [line for line in daily["raw_text"].split("\n") if line.strip()]


def daily_blocks(dailies: list[dict[str, Any]], budget: int | None = None, notes: list[str] | None = None,
                 focus: bool = False) -> str:
    """Daily 원문 블록. pics는 AI 입력에서 제외한다.
    budget(글자 수)을 넘으면 본문을 줄인다. focus=True면 이슈·성과·배운 점 줄은 다른 줄을 먼저 줄인 뒤에야 줄인다."""
    bodies = [_body_lines(d) for d in dailies]
    full = _render_blocks(dailies, bodies)
    if not budget or len(full) <= budget:
        return full
    fixed = len(_render_blocks(dailies, [[] for _ in dailies]))  # 기록 ID·표 등 줄이지 않는 부분
    is_focus = (lambda line: line.strip().startswith(FOCUS_MARKS)) if focus else (lambda line: False)
    size = lambda lines: sum(len(x) + 9 for x in lines)  # noqa: E731 - 줄바꿈·들여쓰기 포함 대략
    room = budget - fixed - sum(size([ln for ln in b if is_focus(ln)]) for b in bodies)
    if room >= 0:
        caps = _fill_caps([size([ln for ln in b if not is_focus(ln)]) for b in bodies], room)
        trimmed = [_cut(b, cap, is_focus) for b, cap in zip(bodies, caps)]
    else:  # 이슈 줄만으로도 넘으면 전체를 균등하게
        caps = _fill_caps([size(b) for b in bodies], budget - fixed)
        trimmed = [_cut(b, cap) for b, cap in zip(bodies, caps)]
    text = _render_blocks(dailies, trimmed)
    if notes is not None:
        cut = sum(1 for b, t in zip(bodies, trimmed) if b != t)
        notes.append(f"업무일지 원문이 {len(full):,}자라 AI 입력 상한 {budget:,}자에 맞춰 기록 {cut}건을 줄여 보냄"
                     f"(→ {len(text):,}자{', 이슈·성과 줄 우선 유지' if focus else ''}). 설정 AI_INPUT_CHARS로 바꿀 수 있음")
    return text


def _render_blocks(dailies: list[dict[str, Any]], bodies: list[list[str]]) -> str:
    blocks = []
    for daily, body_lines in zip(dailies, bodies):
        author = daily.get("author_name") or daily["author"]
        body = "\n        ".join(body_lines)  # 여러 줄 본문(WorkLog 업무일지)은 들여 써서 기록 경계를 분명히
        lines = [
            f"- 기록 ID: {daily['daily_id']} ({daily['date']}, {author}, 카테고리 {daily.get('category') or '없음'})",
            f"  본문: {body}",
        ]
        for table in daily.get("tables", []):
            lines.append(f"  표 [{table['title']}]")
            lines.append("    " + " | ".join(map(str, table["columns"])))
            lines.extend("    " + " | ".join("" if v is None else str(v) for v in row) for row in table["rows"])
        blocks.append("\n".join(lines))
    return "\n".join(blocks) if blocks else "없음"


def item_lines(items: list[dict[str, Any]], *, with_slot: str | None = None) -> str:
    lines = []
    for value in items:
        # 근거 ID는 문장 뒤 [근거: ...]로 분리해 보여 준다. 앞에 (ID)를 붙이면 AI가 문장에 그대로 옮겨 쓴다
        ids = ", ".join(value.get("source_ids", [])) or "없음"
        label = f"[{SLOT_LABEL.get(with_slot, with_slot)}] " if with_slot else ""
        lines.append(f"- {label}{value['text']}  [근거: {ids}]")
    return "\n".join(lines)


def prev_weekly_lines(prev_weekly: dict[str, Any] | None) -> str:
    if not prev_weekly:
        return "없음"
    parts = [item_lines([prev_weekly["headline"]], with_slot="headline")] if prev_weekly.get("headline") else []
    for slot in ("progress", "next_plan", "issues"):
        if prev_weekly.get(slot):
            parts.append(item_lines(prev_weekly[slot], with_slot=slot))
    return "\n".join(p for p in parts if p) or "없음"


def completed_milestones(milestones: list[dict[str, Any]]) -> str:
    done = [f"{m['name']}({m.get('actual') or '완료일 미기재'})" for m in sorted(milestones, key=lambda x: x["order"]) if m["status"] == "완료"]
    return ", ".join(done) if done else "없음"


def weekly_lines(weekly: dict[str, Any]) -> str:
    """cumulative_update 입력: 이번 주 progress, issues."""
    parts = [item_lines(weekly.get(slot, []), with_slot=slot) for slot in ("progress", "issues")]
    return "\n".join(p for p in parts if p) or "없음"


def cumulative_lines(items: list[dict[str, Any]]) -> str:
    return item_lines(items) if items else "없음"
