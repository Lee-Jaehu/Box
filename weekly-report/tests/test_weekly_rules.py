"""weekly 모듈 규칙 테스트 (모두 임시 복사본에서 실행)."""

import hashlib

import pytest

from conftest import ROOT, read, write
from weekly_report.core import ValidationError, previous_week, week_range
from weekly_report.weekly import run_weekly, select_dailies

PID, WEEK = "P-ASM-001", "2026-W39"


def digests(root):
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for d in ("data/master", "data/raw") for p in (root / d).rglob("*.json")}


def test_iso_week_boundaries():
    assert tuple(map(str, week_range("2026-W01"))) == ("2025-12-29", "2026-01-04")
    assert previous_week("2026-W01") == "2025-W52"
    assert previous_week("2021-W01") == "2020-W53"  # 53주 해
    with pytest.raises(ValidationError):
        week_range("2026-W54")


def test_private_and_deleted_memos_are_excluded(repo):
    assert [d["daily_id"] for d in select_dailies(repo, PID, WEEK)] == ["D-260922-ljh-01"]
    path = next((repo / "data/raw/daily").rglob("D-260922-ljh-01.json"))
    daily = read(path)
    daily["deleted"] = True
    write(path, daily)
    assert select_dailies(repo, PID, WEEK) == []


def test_mock_payload_becomes_contract_json_without_touching_inputs(repo, tmp_path):
    before = digests(repo)
    weekly_path, cum_path, report = run_weekly(repo, PID, WEEK, tmp_path / "out")
    weekly, cum = read(weekly_path), read(cum_path)
    assert weekly["meta"]["schema"] == "weekly" and weekly["range"] == {"from": "2026-09-21", "to": "2026-09-27"}
    assert weekly["ai"]["prompt_version"] == "v0.4" and weekly["ai"]["input_revisions"] == {"D-260922-ljh-01": 2}
    assert weekly["no_change"] is False and weekly["review_state"] == "draft"
    assert "new_pinned_facts" not in cum and len(cum["pinned_facts"]) == 2
    text = report.read_text(encoding="utf-8")
    assert "CP-260922-001" in text and "미확정 사이트 코드 ESMI1" in text and "정밀도" in text
    assert report == tmp_path / "out/output/P-ASM-001/validation_2026-W39.txt"  # 과제별로 분리
    assert digests(repo) == before


def test_rerun_increments_revision_and_keeps_created_at(repo, tmp_path):
    first, _, _ = run_weekly(repo, PID, WEEK, tmp_path)
    created = read(first)["meta"]["created_at"]
    run_weekly(repo, PID, WEEK, tmp_path)
    assert read(first)["meta"]["revision"] == 2 and read(first)["meta"]["created_at"] == created


def test_week_without_dailies_skips_ai_and_keeps_cumulative(repo, tmp_path):
    # mock 파일이 없는 주차여도 AI를 부르지 않으므로 성공해야 한다
    weekly_path, cum_path, _ = run_weekly(repo, PID, "2026-W40", tmp_path)
    weekly = read(weekly_path)
    assert weekly["no_change"] is True and weekly["headline"]["text"] == "금주(W40)에는 변경 사항이 없습니다"
    assert weekly["progress"] == [] and weekly["ai"]["model"].startswith("AI 호출 없음")
    prev = read(repo / "data/derived/cumulative/P-ASM-001/2026-W39.json")
    assert read(cum_path)["items"] == prev["items"] and read(cum_path)["pinned_facts"] == prev["pinned_facts"]


def test_changed_rule_uses_previous_weekly(repo, tmp_path):
    prev = read(repo / "data/derived/weekly/P-ASM-001/2026-W39.json")
    prev["week"], prev["range"] = "2026-W38", {"from": "2026-09-14", "to": "2026-09-20"}
    write(tmp_path / "data/derived/weekly/P-ASM-001/2026-W38.json", prev)
    weekly_path, _, report = run_weekly(repo, PID, WEEK, tmp_path)
    weekly = read(weekly_path)
    assert weekly["headline"]["changed"] is True
    assert [i["changed"] for i in weekly["progress"]] == [False, False, False]  # 지난주와 같은 문장
    assert "지난주 비교 결과 False" in report.read_text(encoding="utf-8")


def test_previous_pinned_facts_are_kept_even_if_ai_drops_them(repo, tmp_path):
    path = repo / "data/derived/cumulative/P-ASM-001/2026-W38.json"
    cum = read(path)
    cum["pinned_facts"].append({"text": "이전 고정 사실 유지", "source_ids": ["P-ASM-001"], "kind": "fact", "changed": False})
    write(path, cum)
    _, cum_path, report = run_weekly(repo, PID, WEEK, tmp_path)
    texts = [p["text"] for p in read(cum_path)["pinned_facts"]]
    assert "이전 고정 사실 유지" in texts and len(texts) == len(set(texts)) == 3
    assert "빠진 이전 고정 사실을 코드가 보존" in report.read_text(encoding="utf-8")


def test_structure_error_is_not_saved(repo, tmp_path):
    mock = repo / "prompts/mock_responses/weekly_rollup__P-ASM-001__2026-W39.json"
    payload = read(mock)
    payload["progress"][0]["source_ids"] = ["X-1"]  # 스키마 패턴 위반 (D|P|CP|R)
    write(mock, payload)
    with pytest.raises(ValidationError):
        run_weekly(repo, PID, WEEK, tmp_path)
    assert not (tmp_path / "data/derived/weekly/P-ASM-001/2026-W39.json").exists()


def test_extra_fields_are_dropped_and_bad_milestone_updates_reported(repo, tmp_path):
    mock = repo / "prompts/mock_responses/weekly_rollup__P-ASM-001__2026-W39.json"
    payload = read(mock)
    payload["progress"][0]["confidence"] = 0.9
    payload["milestone_updates"] += [
        {"milestone_id": None, "field": "plan", "to": "2026-09-30", "source_ids": ["D-260922-ljh-01"]},
        {"milestone_id": "M9", "field": "plan", "to": "2026-09-30", "source_ids": ["D-260922-ljh-01"]},
        {"milestone_id": "M6-3", "field": "status", "to": "끝남", "source_ids": ["D-260922-ljh-01"]},
        {"milestone_id": "M6-3", "field": "actual", "to": "2026-02-30", "source_ids": ["D-260922-ljh-01"]},
    ]
    write(mock, payload)
    weekly_path, _, report = run_weekly(repo, PID, WEEK, tmp_path)
    assert "confidence" not in read(weekly_path)["progress"][0]
    text = report.read_text(encoding="utf-8")
    for expected in ("milestone_id가 null", "존재하지 않는 milestone_id M9", "status 값은", "존재하지 않는 날짜"):
        assert expected in text


def test_inputs_from_repo_are_unchanged_by_real_root_run(tmp_path):
    """실제 저장소 root에서 실행해도 master/raw/예시 derived는 바뀌지 않는다 (출력은 tmp)."""
    protected = digests(ROOT)
    examples = {p: p.read_bytes() for p in (ROOT / "data/derived").rglob("*.json")}
    run_weekly(ROOT, PID, WEEK, tmp_path)
    assert digests(ROOT) == protected
    assert {p: p.read_bytes() for p in (ROOT / "data/derived").rglob("*.json")} == examples
