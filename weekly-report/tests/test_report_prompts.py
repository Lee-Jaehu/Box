"""보고 자료(설계 단계): 프롬프트 변수·출력 형식·검사 규칙."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from conftest import ROOT, read
from weekly_report.report_vars import (exec_variables, month_weeks, monthly_variables, render_report_prompt,
                                       report_style_problems)
from weekly_report.validate import build_evidence, check_item

DIRS = [ROOT, ROOT / "demo/w40/out"]
EXAMPLES = ROOT / "docs/보고자료_예시"


def test_month_weeks_follow_iso_thursday_rule():
    assert month_weeks(2026, 10) == ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]
    assert month_weeks(2026, 9) == ["2026-W36", "2026-W37", "2026-W38", "2026-W39"]


@pytest.mark.parametrize("kind", ["report_monthly", "report_exec_summary"])
def test_prompts_render_with_demo_data(kind):
    variables = (monthly_variables(ROOT, ["P-ASM-001"], 2026, 10, DIRS) if kind == "report_monthly"
                 else exec_variables(ROOT, "P-ASM-001", "2026-W40", DIRS))
    system, user = render_report_prompt(ROOT, kind, variables)
    assert "{{" not in system + user
    assert "경어체 완결문" in system and "개조식" in system and "[근거:" in user
    assert "D-261001-ljh-01" in user  # W40 주간 정리본이 들어감
    saved = EXAMPLES / f"{kind}__프롬프트.txt"
    assert saved.read_text(encoding="utf-8") == f"{system}\n\n{user}\n", "docs 예시 프롬프트가 최신이 아님 (scripts 재생성 필요)"


@pytest.mark.parametrize("kind", ["report_monthly", "report_exec_summary"])
def test_example_answers_match_schema_style_and_evidence(kind):
    payload = read(EXAMPLES / f"{kind}__예시응답.json")
    schema = read(ROOT / f"schemas/{kind}.schema.json")
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert report_style_problems(kind, payload) == []
    # 수치·날짜는 입력(주간 정리본·누적 요약·기준정보)에 있는 것만
    project = read(ROOT / "data/master/projects/P-ASM-001.json")
    texts, ids = [], {"P-ASM-001"}
    for base in DIRS:
        for path in list(base.glob("data/derived/weekly/P-ASM-001/*.json")) + list(base.glob("data/derived/cumulative/P-ASM-001/*.json")):
            value = read(path)
            for slot in ("headline", "progress", "next_plan", "issues", "items", "pinned_facts"):
                entries = value.get(slot) or []
                for item in entries if isinstance(entries, list) else [entries]:
                    texts.append(item["text"])
                    ids.update(item.get("source_ids", []))
    evidence = build_evidence(dailies=[], project=project, prev_texts=texts, allowed_ids=ids, prev_level="정보")
    items = []
    for value in payload.values():
        items += [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, dict)]
    errors = [i.format() for item in items for i in check_item("x", item, evidence) if i.level == "오류"]
    assert errors == []


def test_style_checker_catches_common_ai_mistakes():
    payload = read(EXAMPLES / "report_exec_summary__예시응답.json")
    payload["head_message"]["text"] = "재료교체 불량률 개선 효과 유지"  # 경어체 아님
    payload["left_items"][0]["text"] = "1차 로직을 적용했습니다"  # 본문인데 경어체
    payload["emphasis"].append("없는 구절")
    problems = report_style_problems("report_exec_summary", payload)
    assert any("head_message" in p for p in problems) and any("left_items[0]" in p for p in problems)
    assert any("없는 구절" in p for p in problems)
