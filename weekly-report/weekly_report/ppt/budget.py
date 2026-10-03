"""분량 판정·fit_to_budget·페이지 나누기.

- 항목 수(슬롯 한도)와 실제 줄 수(가중 길이 50 기준 줄바꿈)를 따로 센다.
- 글꼴을 줄이거나 도형 밖으로 넘기지 않는다. 넘치면 fit_to_budget(AI)로 줄이고,
  그래도 넘치는 항목은 "(계속)" 장으로 보낸다. 과제당 최대 2장, 그 이상이면 BudgetError.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ..ai import AIError, ExaoneClient
from ..core import render_prompt
from ..prompt_vars import item_lines
from ..textmetrics import line_count, weighted_length
from ..validate import extract_tokens
from .milestones import MsRow
from .model import BodyItem, PageModel, Para, Run, Section, SlideContent

EMU_PER_PT = 12700
EMU_PER_IN = 914400
BODY_PT = 9
LINE_PT = BODY_PT * 1.2  # 9pt 글꼴 100% 줄 간격의 한 줄 높이
MAX_CHARS = 50.0
RULE_LINES = 36  # CLAUDE.md: 본문 전체 36줄 (배경/목표 + 마일스톤 표 행 + 진행 현황·계획·이슈)
BODY_TOP_MAX_LINES = 3
GAP_EMU = int(0.06 * EMU_PER_IN)
INSET_EMU = int(0.04 * EMU_PER_IN)


class BudgetError(ValueError):
    """과제당 2장 안에 넣을 수 없음."""


@dataclass
class Geometry:
    """템플릿에서 읽은 배치 기준 (단위 EMU)."""

    area_top: int  # main_table r2 위쪽
    area_bottom: int  # main_table r2 아래쪽
    ms_col_widths: list[int]
    ms_row_height: int
    ms_cell_margin: int  # 좌우 여백 합

    @property
    def line_emu(self) -> int:
        return int(LINE_PT * EMU_PER_PT)


def para_lines(para: Para, width: float = MAX_CHARS) -> int:
    if para.kind == "blank":
        return 1
    return line_count(para.text, width)


def cell_width_chars(width_emu: int, margin_emu: int) -> float:
    """셀 너비 → 가중 글자 수 (한글 1자 ≈ 9pt 폭)."""
    return max(1.0, (width_emu - margin_emu) / EMU_PER_PT / BODY_PT)


def ms_row_lines(row: MsRow, geom: Geometry) -> int:
    return max(line_count(text or " ", cell_width_chars(w, geom.ms_cell_margin)) for text, w in zip(row.cells, geom.ms_col_widths))


def ms_row_height(row: MsRow, geom: Geometry) -> int:
    lines = ms_row_lines(row, geom)
    return max(geom.ms_row_height, int(lines * geom.line_emu + 2 * 9144))


def ms_table_height(rows: list[MsRow], geom: Geometry) -> int:
    return geom.ms_row_height + sum(ms_row_height(r, geom) for r in rows)


def body_capacity(geom: Geometry, top_lines: int, ms_rows: list[MsRow]) -> tuple[int, int]:
    """(물리 가용 줄 수, 36줄 규칙 가용 줄 수)."""
    used = INSET_EMU
    if top_lines:
        used += top_lines * geom.line_emu + GAP_EMU
    used += ms_table_height(ms_rows, geom) + GAP_EMU + INSET_EMU
    physical = (geom.area_bottom - geom.area_top - used) // geom.line_emu
    rule = RULE_LINES - top_lines - (len(ms_rows) + 1)
    return int(physical), rule


# ---------------------------------------------------------------- 슬롯 분량 검사·fit_to_budget

def slot_problems(section: Section) -> list[str]:
    problems = []
    if len(section.items) > section.limit:
        problems.append(f"항목 {len(section.items)}개 > 한도 {section.limit}개")
    for index, item in enumerate(section.items):
        if weighted_length(item.text) > MAX_CHARS:
            problems.append(f"[{index}] {weighted_length(item.text):.1f}자 > {MAX_CHARS:g}자")
    return problems


def _numbers(text: str) -> set[str]:
    tokens = extract_tokens(text)
    return set(tokens.numbers) | {f"{m}/{d}" for m, d in tokens.dates} | set(tokens.codes) | set(tokens.units)


def _best_match(text: str, sources: list[str], originals: list[BodyItem]) -> BodyItem | None:
    candidates = [o for o in originals if set(sources) & set(o.source_ids)] or ([o for o in originals if not o.source_ids] if not sources else [])
    if not candidates:
        return None
    return max(candidates, key=lambda o: SequenceMatcher(None, text, o.text).ratio())


def check_fit_result(payload: dict[str, Any], originals: list[BodyItem], limit: int) -> tuple[list[BodyItem], list[BodyItem]]:
    """fit_to_budget 결과 검증 + changed/kind 승계. 실패하면 ValueError."""
    if not isinstance(payload.get("items"), list) or not isinstance(payload.get("dropped", []), list):
        raise ValueError("items/dropped 배열이 아님")
    allowed_ids = {s for o in originals for s in o.source_ids}
    original_tokens = set().union(*(_numbers(o.text) for o in originals)) if originals else set()
    kept: list[BodyItem] = []
    dropped: list[BodyItem] = []
    for group in ("items", "dropped"):
        for index, value in enumerate(payload.get(group, [])):
            if not isinstance(value, dict) or not isinstance(value.get("text"), str):
                raise ValueError(f"{group}[{index}] 형식 오류")
            sources = list(value.get("source_ids") or [])
            if not set(sources) <= allowed_ids:
                raise ValueError(f"{group}[{index}] 원본에 없는 근거 {sorted(set(sources) - allowed_ids)}")
            extra = _numbers(value["text"]) - original_tokens
            if extra:
                raise ValueError(f"{group}[{index}] 원본에 없는 수치·날짜·코드 {sorted(extra)}")
            match = _best_match(value["text"], sources, originals)
            if match is None:
                raise ValueError(f"{group}[{index}] 원본 항목과 연결할 수 없음")
            if group == "dropped":
                # 문서 규칙: 뺀 항목은 원문 그대로 → 원본 항목을 그대로 (계속)으로 보낸다
                dropped.append(replace(match, overflow=True))
            else:
                kept.append(BodyItem(value["text"], sources, match.changed, match.kind, match.blue))
    if len(kept) > limit:
        raise ValueError(f"items {len(kept)}개 > 한도 {limit}개")
    for item in kept:
        if weighted_length(item.text) > MAX_CHARS:
            raise ValueError(f"줄인 문장이 여전히 {MAX_CHARS:g}자 초과: {item.text}")
    covered = {id(o) for o in originals if any(_best_match(k.text, k.source_ids, originals) is o for k in kept)}
    covered |= {id(o) for o in originals if any(d.text == o.text for d in dropped)}
    missing = [o.text for o in originals if id(o) not in covered]
    if missing:
        raise ValueError(f"원본 항목 누락: {missing}")
    return kept, dropped


def fit_sections(content: SlideContent, client: ExaoneClient | None, root: Path) -> list[str]:
    """슬롯 한도·50자 초과 시 fit_to_budget 호출. 검증에 실패하면 원문 유지 + 초과분 (계속)."""
    notes: list[str] = []
    for section in content.sections:
        problems = slot_problems(section)
        if not problems:
            continue
        notes.append(f"{section.key}: 분량 초과 ({'; '.join(problems)})")
        originals = list(section.items)
        if client is not None:
            variables = {"slot_name": section.key, "max_items": section.limit, "max_chars": int(MAX_CHARS),
                         "item_lines": item_lines([{"text": i.text, "source_ids": i.source_ids} for i in originals])}
            try:
                system, user = render_prompt(root, "fit_to_budget", variables)
                payload = client.complete("fit_to_budget", content.project_id, content.week, system, user, variant=section.key)
                kept, dropped = check_fit_result(payload, originals, section.limit)
                section.items = kept + dropped
                notes.append(f"{section.key}: fit_to_budget 적용 (유지 {len(kept)}개, (계속) {len(dropped)}개, changed 승계)")
            except (AIError, ValueError, KeyError, json.JSONDecodeError) as exc:
                notes.append(f"{section.key}: fit_to_budget 미적용 → 원문 유지 ({exc})")
        # 그래도 한도를 넘는 항목은 (계속)으로 보낸다
        visible = [i for i in section.items if not i.overflow]
        for item in visible[section.limit:]:
            item.overflow = True
        if len(visible) > section.limit:
            notes.append(f"{section.key}: 한도 초과 {len(visible) - section.limit}개 항목을 (계속) 장으로 이월")
    return notes


# ---------------------------------------------------------------- 페이지 나누기

def _heading(section: Section, continued: bool) -> Para:
    return Para([Run(f"[{section.heading}{' (계속)' if continued else ''}]", bold=True)], "heading")


def _item(item: BodyItem) -> Para:
    return Para([Run(f" - {item.text}", blue=item.blue)], "item")


def _layout_body(sections: list[tuple[Section, list[BodyItem], bool]], capacity: int) -> tuple[list[Para], list[tuple[Section, list[BodyItem], bool]], int]:
    """capacity 줄 안에 섹션을 순서대로 채운다. (문단, 남은 섹션, 사용 줄 수)"""
    paras: list[Para] = []
    used = 0
    rest: list[tuple[Section, list[BodyItem], bool]] = []
    for position, (section, items, continued) in enumerate(sections):
        if rest:
            rest.append((section, items, continued))
            continue
        lead = ([Para([Run("")], "blank")] if paras else [])
        head = lead + [_heading(section, continued)]
        head_lines = sum(para_lines(p) for p in head)
        placed = 0
        block: list[Para] = []
        block_lines = head_lines
        for item in items:
            lines = line_count(item.text, MAX_CHARS)
            if used + block_lines + lines > capacity:
                break
            block.append(_item(item))
            block_lines += lines
            placed += 1
        if placed == 0 and items:
            rest.append((section, items, continued))
            continue
        paras.extend(head + block)
        used += block_lines
        if placed < len(items):
            rest.append((section, items[placed:], True))
    return paras, rest, used


def paginate(content: SlideContent, geom: Geometry) -> tuple[list[PageModel], list[str]]:
    notes: list[str] = []
    top_lines = sum(para_lines(p) for p in content.body_top)
    if top_lines > BODY_TOP_MAX_LINES:
        notes.append(f"배경/목표 {top_lines}줄 > {BODY_TOP_MAX_LINES}줄 (기준정보 문장이라 자동으로 줄이지 않음)")

    first = [(s, [i for i in s.items if not i.overflow], False) for s in content.sections]
    carried = [(s, [i for i in s.items if i.overflow], True) for s in content.sections if any(i.overflow for i in s.items)]

    physical, rule = body_capacity(geom, top_lines, content.ms_rows)
    capacity = min(physical, rule)
    paras, rest, used = _layout_body(first, capacity)
    pages = [PageModel(False, content.pjt_name, content.body_top, content.ms_rows, paras, used, capacity,
                       top_lines + len(content.ms_rows) + 1 + used)]

    # 같은 섹션의 넘친 부분과 (계속)으로 보낸 항목을 원래 순서대로 합친다
    merged: dict[str, tuple[Section, list[BodyItem], bool]] = {}
    for section, items, cont in rest + carried:
        if section.key in merged:
            merged[section.key][1].extend(items)
        else:
            merged[section.key] = (section, list(items), cont)
    remaining = [merged[s.key] for s in content.sections if s.key in merged]

    if remaining or content.ms_overflow:
        physical2, rule2 = body_capacity(geom, 0, content.ms_overflow)
        capacity2 = min(physical2, rule2)
        paras2, rest2, used2 = _layout_body(remaining, capacity2)
        if rest2:
            left = sum(len(items) for _, items, _ in rest2)
            raise BudgetError(f"{content.project_id}: (계속) 장까지 써도 본문 {left}개 항목이 넘침 (과제당 최대 2장)")
        pages.append(PageModel(True, content.pjt_name.rsplit(" (", 1)[0] + " (계속)", [], content.ms_overflow, paras2, used2, capacity2,
                               len(content.ms_overflow) + (1 if content.ms_overflow else 0) + used2))
        notes.append(f"(계속) 장 생성: 본문 {sum(len(i) for _, i, _ in remaining)}개 항목, 마일스톤 {len(content.ms_overflow)}행")
    for index, page in enumerate(pages, 1):
        notes.append(f"{index}장: 본문 {page.body_lines}/{page.body_capacity}줄 사용 (36줄 규칙 기준 총 {page.rule_lines}줄)")
    return pages, notes
