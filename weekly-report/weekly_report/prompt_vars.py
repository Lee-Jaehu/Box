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
        lines.append(
            f"- {m['milestone_id']} | {m['name']} | 적용 범위: {codes.scope_label(m['scope'])} | "
            f"Baseline {m.get('baseline') or '-'} | 계획 {plan} | 상태 {m['status']}"
        )
    return "\n".join(lines) if lines else "없음"


def daily_blocks(dailies: list[dict[str, Any]]) -> str:
    """Daily 원문 블록. pics는 AI 입력에서 제외한다."""
    blocks = []
    for daily in dailies:
        lines = [
            f"- 기록 ID: {daily['daily_id']} ({daily['date']}, {daily['author']}, 카테고리 {daily.get('category') or '없음'})",
            f"  본문: {daily['raw_text']}",
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
        ids = ",".join(value.get("source_ids", [])) or "근거 없음"
        label = f"[{SLOT_LABEL.get(with_slot, with_slot)}] " if with_slot else ""
        lines.append(f"- {label}({ids}) {value['text']}")
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
