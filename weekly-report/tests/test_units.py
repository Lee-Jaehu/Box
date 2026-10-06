"""분량 계산·코드표·의미 검증·AI 클라이언트 단위 테스트."""

import json
import urllib.error
from pathlib import Path

import pytest

from conftest import ROOT, read
from weekly_report.ai import AIError, ExaoneClient, MockResponseMissing, ResponseFormatError, read_payload
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
    assert client.complete("free_form", "P", "2026-W39", "s", "u") == {"ok": 1}
    assert len(transport.bodies) == 2 and "JSON" in transport.bodies[1]["messages"][-1]["content"]


def test_live_retries_once_on_wrong_shape(monkeypatch):
    monkeypatch.setenv("EXAONE_API_URL", "https://exaone.invalid/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "secret-key-123")
    good = {"items": [{"text": "A 완료", "source_ids": ["D-1"]}]}
    transport = FakeTransport([{"content": json.dumps({"summary": "x"})},
                               {"content": "결과입니다.\n```json\n" + json.dumps({"result": good}) + "\n```\n참고하세요."}])
    client = ExaoneClient(ROOT, "live", transport=transport)
    assert client.complete("cumulative_update", "P", "2026-W39", "s", "u") == good
    assert '"items" 배열' in transport.bodies[1]["messages"][-1]["content"]


def test_read_payload_accepts_common_ai_variants():
    item = {"text": "A 완료", "source_ids": ["D-1"]}
    variants = [
        "누적 요약입니다.\n```json\n" + json.dumps({"items": [item]}) + "\n```",
        json.dumps({"cumulative_update": {"items": [item], "pinned_facts": []}}),
        json.dumps({"items": [item]}) + "\n\n위와 같이 정리했습니다.",
        json.dumps([item]),
    ]
    for text in variants:
        assert read_payload(text, "cumulative_update")["items"] == [item], text
    assert read_payload(json.dumps({"items": ["A 완료"]}), "cumulative_update")["items"] == [{"text": "A 완료", "source_ids": []}]


def test_read_payload_explains_wrong_shape():
    with pytest.raises(ResponseFormatError, match="받은 최상위 키: summary, pinned_facts"):
        read_payload(json.dumps({"summary": ["A"], "pinned_facts": []}), "cumulative_update")
    with pytest.raises(ResponseFormatError, match="weekly_rollup"):
        read_payload(json.dumps({"headline": {"text": "h"}, "progress": []}), "cumulative_update")
    with pytest.raises(ResponseFormatError, match=r"items\[1\]"):
        read_payload(json.dumps({"items": [{"text": "a"}, {"txt": "b"}]}), "cumulative_update")


def test_live_errors_do_not_leak_key(monkeypatch):
    monkeypatch.setenv("EXAONE_API_URL", "https://exaone.invalid/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "secret-key-123")
    for error in (TimeoutError(), urllib.error.HTTPError("u", 500, "x", {}, None), urllib.error.URLError(OSError("down"))):
        client = ExaoneClient(ROOT, "live", transport=FakeTransport([error] * 4))  # 일시 오류는 2번 더, 5xx는 호환 형식으로 1번 더
        client.sleep = lambda seconds: None
        with pytest.raises(AIError) as info:
            client.complete("p", "P", "W", "s", "u")
        sends = "요청 4회" if isinstance(error, urllib.error.HTTPError) else "요청 3회"
        assert "secret-key-123" not in str(info.value) and sends in str(info.value)
    bad = FakeTransport([{"content": "x"}, {"content": "y"}])
    with pytest.raises(AIError, match="2회"):
        ExaoneClient(ROOT, "live", transport=bad).complete("p", "P", "W", "s", "u")


def test_live_reads_json_after_think_and_retries_gateway_error(monkeypatch):
    """사고형 모델: <think> 안의 { }를 건너뛰고, 게이트웨이 일시 오류(500)는 대기 후 다시 보낸다."""
    monkeypatch.setenv("EXAONE_API_URL", "https://exaone.invalid/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "k")
    answer = {"choices": [{"finish_reason": "stop", "message": {"content": '<think>{형식}</think>\n{"items": [{"text": "a", "source_ids": []}]}'}}]}
    client = ExaoneClient(ROOT, "live", transport=FakeTransport([urllib.error.HTTPError("u", 500, "x", {}, None), answer]))
    waits = []
    client.sleep = waits.append
    assert client.complete("cumulative_update", "P", "W", "s", "u")["items"][0]["text"] == "a"
    assert waits == [3.0] and client.call_log[0]["sends"] == 2
    cut = {"choices": [{"finish_reason": "length", "message": {"content": None, "reasoning": "생각"}}]}
    with pytest.raises(AIError, match="길이 한도"):
        ExaoneClient(ROOT, "live", transport=FakeTransport([cut])).complete("cumulative_update", "P", "W", "s", "u")


def test_live_switches_to_compat_shape_when_gateway_keeps_failing(monkeypatch):
    monkeypatch.setenv("EXAONE_API_URL", "https://exaone.invalid/v1")
    monkeypatch.setenv("EXAONE_API_KEY", "k")
    ok = {"choices": [{"message": {"content": '{"items": [{"text": "a", "source_ids": []}]}'}}]}
    error = urllib.error.HTTPError("u", 500, "x", {}, None)
    transport = FakeTransport([error, error, error, ok])
    client = ExaoneClient(ROOT, "live", transport=transport)
    client.sleep = lambda seconds: None
    assert client.complete("cumulative_update", "P", "W", "SYS", "USER")["items"]
    assert transport.bodies[-1]["messages"] == [{"role": "user", "content": "SYS\n\nUSER"}] and "temperature" not in transport.bodies[-1]


def test_live_requires_env(monkeypatch):
    monkeypatch.delenv("EXAONE_API_URL", raising=False)
    with pytest.raises(AIError, match="EXAONE_API_URL"):
        ExaoneClient(ROOT, "live").complete("p", "P", "W", "s", "u")


def test_mock_missing_file():
    with pytest.raises(MockResponseMissing):
        ExaoneClient(ROOT).complete("weekly_rollup", "P-NONE-999", "2026-W39", "s", "u")


def test_lg_smart_font_files_match_ea_name():
    from weekly_report.fonts import EA_BOLD, EA_REGULAR, load_fonts

    fonts = load_fonts(ROOT)
    assert fonts.regular is not None and fonts.regular.path.name == "LGSMHAR_V1.4_151215.TTF"
    assert EA_BOLD in fonts.fonts  # 굵은 글꼴 파일도 이름 확인
    assert fonts.hangul_em == pytest.approx(0.891, abs=0.001)
    assert fonts.regular.embeddable


def test_fonts_fallback_without_files(tmp_path):
    from weekly_report.fonts import load_fonts

    fonts = load_fonts(tmp_path)
    assert fonts.regular is None and fonts.hangul_em == 1.0 and "글꼴 파일 없음" in fonts.summary()[0]


def test_paginate_counts_rendered_bullet_prefix():
    from weekly_report.ppt.budget import _layout_body
    from weekly_report.ppt.model import BodyItem, Section

    text = "가" * 49 + "a"  # 49.55자: 본문만 세면 1줄, "- " 접두를 붙이면 2줄
    assert line_count(text) == 1 and line_count("- " + text) == 2
    section = Section("progress", "진행", [BodyItem(text, ["D-1"])], 7)
    paras, rest, used = _layout_body([(section, section.items, False)], capacity=2, width=50.0)
    # 제목 1줄 + 항목 2줄 = 3줄 → 2줄 용량에는 넣지 않고 (계속)으로 넘긴다
    assert paras == [] and used == 0 and rest[0][1] == section.items


def test_preview_removes_stale_slide_images(tmp_path, monkeypatch):
    import subprocess

    from weekly_report import preview

    out = tmp_path / "preview"
    out.mkdir()
    (out / "deck-1.png").write_bytes(b"old")
    (out / "deck-2.png").write_bytes(b"old")  # 이전 실행의 2장째 (지금 덱은 1장)
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"x")

    def fake_run(cmd, **kwargs):
        if "--convert-to" in cmd:
            (Path(cmd[cmd.index("--outdir") + 1]) / "deck.pdf").write_bytes(b"%PDF")
        elif cmd[0].endswith("pdftoppm"):
            Path(cmd[-1] + "-1.png").write_bytes(b"new")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(preview.shutil, "which", lambda name: None if name == "pdffonts" else f"/usr/bin/{name}")
    monkeypatch.setattr(preview.subprocess, "run", fake_run)
    images, _ = preview.render_preview(tmp_path, pptx, out)
    assert [p.name for p in images] == ["deck-1.png"] and (out / "deck-1.png").read_bytes() == b"new"


def _open_files(suffix):
    import os

    found = []
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if target.endswith(suffix):
            found.append(target)
    return found


@pytest.mark.skipif(not Path("/proc/self/fd").exists(), reason="리눅스 /proc 필요")
def test_font_files_are_closed_after_reading(tmp_path):
    """Windows에서는 열린 파일을 지울 수 없다 → 글꼴 실측 후 파일 핸들이 남으면 작업공간 초기화가 실패한다."""
    import shutil as sh

    from weekly_report.fonts import load_fonts

    sh.copy(ROOT / "LGSMHAR_V1.4_151215.TTF", tmp_path)
    assert load_fonts(tmp_path).regular is not None
    assert not [f for f in _open_files(".TTF") if str(tmp_path) in f]


def test_sentence_rules_polite_40_to_60_chars_with_date():
    from weekly_report.textmetrics import has_date_note, is_polite, sentence_problems

    good = "북미 Site 수평전개를 적용하고, 적용 전 현지 PLC 보정 파라미터 이식을 검증할 예정입니다. (~10/13)"
    assert sentence_problems(good, need_date=True) == []
    assert is_polite("원격 접속 지원 여부를 IT팀에 확인 요청드립니다 (지원 요청). (10/01)")
    assert is_polite("추가 모니터링이 필요할 것으로 보입니다(판단).")
    for note in ("(10/08)", "(09/28~09/30)", "(~10/16)", "(09/04~)"):
        assert has_date_note(f"수평전개를 완료했습니다. {note}"), note
    assert not has_date_note("WA 4대(#21~#24)에 적용했습니다")  # 문장 안 괄호는 날짜 표시가 아님
    short = sentence_problems("수평전개 누적 26대")  # 예전 개조식: 짧고 명사형 종결
    assert any("최소 40자" in p for p in short) and any("경어체" in p for p in short)
    assert any("날짜" in p for p in sentence_problems("가" * 40 + "했습니다", need_date=True))
    assert any("최대 60자" in p for p in sentence_problems("가" * 58 + "했습니다"))


def test_prompts_ask_for_polite_full_sentences():
    from weekly_report.core import render_prompt

    system, _ = render_prompt(ROOT, "fit_to_budget", {"slot_name": "progress", "max_items": 7, "max_chars": 60,
                                                       "min_chars": 40, "item_lines": "- x"})
    assert "~습니다/~니다" in system and "40자 이상 60자 이내" in system and "개조식으로 쓴다" not in system
    assert '"(MM/DD)"' in system and "메모의 작성일" in system


def test_record_ids_copied_into_text_are_moved_to_source_ids():
    """실제 EXAONE 응답(사용자 Example): 프롬프트의 "(P-ASM-001) 문장"을 따라 문장 앞에 ID를 붙여 옴."""
    answer = {"items": [{"text": "(P-ASM-001) 1차 로직을 적용해 E77 불량률이 0.189% → 0.164%로 감소했습니다", "source_ids": ["D-261005-jaehu-01"]},
                        {"text": "수평전개를 9/16 완료했습니다  [근거: D-260930-khw-01]", "source_ids": ["D-260930-khw-01"]}],
              "pinned_facts": [{"text": "(D-260922-ljh-01) ESWA 2차 로직 적용 후 0.171% → 0.144% (4일 단기)", "source_ids": []}]}
    value = read_payload(json.dumps(answer, ensure_ascii=False), "cumulative_update")
    assert value["items"][0] == {"text": "1차 로직을 적용해 E77 불량률이 0.189% → 0.164%로 감소했습니다",
                                 "source_ids": ["D-261005-jaehu-01", "P-ASM-001"]}
    assert value["items"][1]["text"] == "수평전개를 9/16 완료했습니다"
    assert value["pinned_facts"][0] == {"text": "ESWA 2차 로직 적용 후 0.171% → 0.144% (4일 단기)", "source_ids": ["D-260922-ljh-01"]}
    # 문장 안의 괄호(호기·기간)는 그대로 둔다
    keep = read_payload(json.dumps({"items": [{"text": "(4일 단기) 효과를 확인했습니다", "source_ids": []}]}, ensure_ascii=False), "cumulative_update")
    assert keep["items"][0]["text"] == "(4일 단기) 효과를 확인했습니다"


def test_prompt_lists_sources_after_text_not_as_prefix():
    from weekly_report.prompt_vars import cumulative_lines

    text = cumulative_lines([{"text": "1차 적용 E77 0.189% → 0.164%", "source_ids": ["P-ASM-001"]}])
    assert text == "- 1차 적용 E77 0.189% → 0.164%  [근거: P-ASM-001]"
