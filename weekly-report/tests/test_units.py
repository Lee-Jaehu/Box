"""분량 계산·코드표·의미 검증·AI 클라이언트 단위 테스트."""

import json
import urllib.error

import pytest

from conftest import ROOT, read
from weekly_report.ai import AIError, ExaoneClient, MockResponseMissing
from weekly_report.codes import CodeTable
from weekly_report.textmetrics import line_count, weighted_length, wrap_text
from weekly_report.validate import build_evidence, check_item, extract_tokens
from weekly_report.weekly import _semantic_issues


def test_weighted_length_and_wrap():
    assert weighted_length("한A1-") == pytest.approx(2.65)
    assert line_count("가" * 50) == 1 and line_count("가" * 51) == 2
    # 영문·숫자는 0.55: 90자 = 49.5 → 1줄
    assert line_count("a" * 90) == 1
    assert all(weighted_length(line) <= 50 for line in wrap_text("가나다 " * 40))


def test_code_labels_and_site_alias():
    codes = CodeTable.load(ROOT)
    assert codes.scope_label("common") == "공통"
    assert codes.scope_label([{"site": "WA", "line": "MEB", "process": "AS"}]) == "WA MEB·조립"
    assert codes.scope_label([{"region": "NA", "process": "AS"}]) == "북미·조립"
    assert "#2-2·3" in codes.target_label([{"site": "MI_HL", "process": "AS", "units": ["#2-2", "#2-3"]}])
    assert codes.resolve_site_alias("ESWA") == "WA"
    assert codes.resolve_site_alias("ESMI1") is None  # MI1은 미확정 → 정상 코드로 처리하지 않음
    assert codes.unresolved_site_tokens("ESWA, ESMI1, ESS") == ["ESMI1"]


def test_tokens_separate_dates_ids_units_codes():
    t = extract_tokens("ESMI1 #2-2·3 0.367% → 0.230%, 9/30 완료 (M6-3, W39)")
    assert t.dates == [(9, 30)] and t.units == ["#2-2·3"] and "M6-3" in t.ids
    assert t.numbers == ["0.367%", "0.230%"] and set(t.codes) == {"ESMI1", "W39"}


def _evidence(raw, prev=(), computed=()):
    project = read(ROOT / "data/master/projects/P-ASM-001.json")
    return build_evidence(dailies=[{"raw_text": raw}], project=project, prev_texts=prev, computed=computed,
                          allowed_ids={"D-1", "P-ASM-001"}, codes=CodeTable.load(ROOT))


def test_semantic_number_sources_are_distinguished():
    ev = _evidence("불량률 0.23 확인, 4일 비교", prev=["예전 0.555"], computed=["W39"])
    levels = lambda text: [(i.level, i.message) for i in check_item("x", {"text": text, "source_ids": ["D-1"]}, ev)]
    assert levels("0.23 확인") == []
    assert levels("0.230 확인")[0][0] == "주의" and "정밀도" in levels("0.230 확인")[0][1]
    assert levels("4일") == []
    assert levels("금주(W39)") == []  # 계산값
    assert "이전 요약" in levels("0.555 유지")[0][1]
    assert levels("7% 개선")[0][0] == "오류"  # 어디에도 없는 수치
    assert levels("10/32 예정")[0][0] == "오류"  # 존재하지 않는 날짜


def test_semantic_issue_wrapper_detects_4_and_unknown_source():
    project = read(ROOT / "data/master/projects/P-ASM-001.json")
    bad = {"headline": {"text": "입력에 없는 7.5% 개선", "source_ids": ["P-ASM-001"]}, "progress": [], "next_plan": [], "issues": [], "milestone_updates": []}
    assert any("수치" in x for x in _semantic_issues(bad, {"P-ASM-001"}, project, "입력 수치 없음"))
    bad["headline"] = {"text": "근거 검사", "source_ids": ["CP-260922-001"]}
    assert any("근거" in x for x in _semantic_issues(bad, {"P-ASM-001"}, project, ""))


class FakeTransport:
    def __init__(self, replies):
        self.replies, self.bodies = list(replies), []

    def request(self, url, key, body, timeout):
        self.bodies.append(json.loads(json.dumps(body)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply).encode()


def test_live_retries_once_on_non_json(monkeypatch):
    monkeypatch.setenv("EXAONE_API_URL", "https://exaone.invalid/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "secret-key-123")
    transport = FakeTransport([{"choices": [{"message": {"content": "죄송합니다"}}]},
                               {"choices": [{"message": {"content": "```json\n{\"ok\": 1}\n```"}}]}])
    client = ExaoneClient(ROOT, "live", transport=transport)
    assert client.complete("weekly_rollup", "P", "2026-W39", "s", "u") == {"ok": 1}
    assert len(transport.bodies) == 2 and "JSON" in transport.bodies[1]["messages"][-1]["content"]


def test_live_errors_do_not_leak_key(monkeypatch):
    monkeypatch.setenv("EXAONE_API_URL", "https://exaone.invalid/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "secret-key-123")
    for error in (TimeoutError(), urllib.error.HTTPError("u", 500, "x", {}, None), urllib.error.URLError(OSError("down"))):
        with pytest.raises(AIError) as info:
            ExaoneClient(ROOT, "live", transport=FakeTransport([error])).complete("p", "P", "W", "s", "u")
        assert "secret-key-123" not in str(info.value)
    bad = FakeTransport([{"content": "x"}, {"content": "y"}])
    with pytest.raises(AIError, match="2회"):
        ExaoneClient(ROOT, "live", transport=bad).complete("p", "P", "W", "s", "u")


def test_live_requires_env(monkeypatch):
    monkeypatch.delenv("EXAONE_API_URL", raising=False)
    with pytest.raises(AIError, match="EXAONE_API_URL"):
        ExaoneClient(ROOT, "live").complete("p", "P", "W", "s", "u")


def test_mock_missing_file():
    with pytest.raises(MockResponseMissing):
        ExaoneClient(ROOT).complete("weekly_rollup", "P-NONE-999", "2026-W39", "s", "u")
