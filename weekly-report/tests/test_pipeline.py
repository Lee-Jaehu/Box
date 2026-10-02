import hashlib
import json
import shutil
from pathlib import Path

import pytest

from weekly_report.core import previous_week, week_range, weighted_length
from weekly_report.pptgen import apply_updates, collapse_milestones, generate_ppt
from weekly_report.weekly import run_weekly, select_dailies

ROOT = Path(__file__).parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_week_boundary():
    assert tuple(map(str, week_range("2026-W01"))) == ("2025-12-29", "2026-01-04")
    assert previous_week("2026-W01") == "2025-W52"


def test_daily_filter_excludes_private_and_deleted(tmp_path):
    assert [d["daily_id"] for d in select_dailies(ROOT, "P-ASM-001", "2026-W39")] == ["D-260922-ljh-01"]
    copy = tmp_path / "repo"; shutil.copytree(ROOT, copy)
    path = next((copy / "data/raw/daily").rglob("D-260922*.json")); value = json.loads(path.read_text()); value["deleted"] = True; path.write_text(json.dumps(value))
    assert select_dailies(copy, "P-ASM-001", "2026-W39") == []


def test_mock_payload_becomes_contract_json_and_preserves_inputs(tmp_path):
    protected = list((ROOT / "data/master").rglob("*.json")) + list((ROOT / "data/raw").rglob("*.json")); before = {p: digest(p) for p in protected}
    weekly, cumulative, report = run_weekly(ROOT, "P-ASM-001", "2026-W39", tmp_path)
    w, c = json.loads(weekly.read_text()), json.loads(cumulative.read_text())
    assert w["meta"]["schema"] == "weekly" and w["project_id"] == "P-ASM-001"
    assert "new_pinned_facts" not in c and len(c["pinned_facts"]) == 2
    assert "CP-260922-001" in report.read_text()  # mock의 잘못된 근거를 숨기지 않는다.
    assert "표시 정밀도" in report.read_text() and "미확정 사이트 코드 ESMI1" in report.read_text()
    assert before == {p: digest(p) for p in protected}


def test_no_data_does_not_need_mock_and_keeps_cumulative(tmp_path):
    weekly, cumulative, _ = run_weekly(ROOT, "P-ASM-001", "2026-W40", tmp_path)
    assert json.loads(weekly.read_text())["no_change"] is True
    # 저장소에는 W39 이전 누적이 있으나 out-root가 분리돼도 입력 누적을 유지한다.
    assert json.loads(cumulative.read_text())["items"] == json.loads((ROOT / "data/derived/cumulative/P-ASM-001/2026-W39.json").read_text())["items"]


def test_invalid_milestone_updates_are_reported_and_baseline_unchanged():
    project = json.loads((ROOT / "data/master/projects/P-ASM-001.json").read_text())
    weekly = {"milestone_updates": [{"milestone_id": None, "field": "plan", "to": "2026-10-01"}, {"milestone_id": "M6-3", "field": "status", "to": 3}]}
    result, warnings, _ = apply_updates(project, weekly)
    assert len(warnings) == 2 and result["milestones"][7]["baseline"] == "2026-09-25"


def test_weight_and_completed_row_collapse():
    assert weighted_length("한A1-") == pytest.approx(2.65)
    rows = [{"milestone_id": f"M6-{i}", "parent_id": "M6", "status": "완료", "order": i, "name": "전개", "scope": "common", "baseline": None, "plan": None, "actual": None, "note": None} for i in range(1, 11)]
    assert len(collapse_milestones(rows)) <= 9


def test_missing_template_reports_required_shapes(tmp_path):
    with pytest.raises(FileNotFoundError, match="main_table"):
        generate_ppt(ROOT, ROOT / "data/master/projects/P-ASM-001.json", ROOT / "data/derived/weekly/P-ASM-001/2026-W39.json", ROOT / "data/derived/cumulative/P-ASM-001/2026-W39.json", tmp_path / "missing.pptx", tmp_path / "out.pptx")
