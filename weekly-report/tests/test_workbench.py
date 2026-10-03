"""웹 테스트 화면: 작업공간 로직과 HTTP 스모크 테스트."""

import hashlib
import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import ROOT, read
from weekly_report import workbench as wb
from weekly_report.webapp import make_server


def digests():
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for d in ("data", "prompts") for p in (ROOT / d).rglob("*.json")}


@pytest.fixture
def ws(tmp_path):
    return wb.init_workspace(tmp_path / "ws")


def test_init_workspace_includes_w40_demo_and_keeps_repo(ws):
    before = digests()
    dailies = wb.list_dailies(ws, "P-ASM-001", "2026-W40")
    excluded = {d["daily_id"]: d["excluded"] for d in dailies}
    assert excluded["D-260929-ljh-01"] == "개인 메모" and excluded["D-261001-ljh-02"] == "삭제됨"
    assert sum(v is None for v in excluded.values()) == 5
    assert (ws / "prompts/mock_responses/weekly_rollup__P-ASM-001__2026-W40.json").exists()
    assert wb.list_projects(ws)[0]["project_id"] == "P-ASM-001"
    assert digests() == before


def test_run_w40_with_demo_responses(ws):
    result = wb.run(ws, "P-ASM-001", "2026-W40")
    assert result["status"] == "ok" and not result["problems"]
    assert result["files"]["pptx"] == "output/P-ASM-001_2026-W40.pptx"
    assert "슬라이드: 1장" in result["ppt_check"]
    assert (ws / result["files"]["pptx"]).exists()


def test_new_week_asks_for_prompt_then_completes(ws):
    saved = wb.save_daily(ws, {"date": "2026-10-06", "author": "ljh", "visibility": "project", "project_id": "P-ASM-001",
                               "category": "ROLL", "raw_text": "북미 적용 준비 회의 진행. PLC 펌웨어 검증 계획 수립.",
                               "table_title": "점검", "table_text": "항목\t결과\nPLC 버전\t확인 중"})
    assert saved["daily_id"] == "D-261006-ljh-01" and saved["tables"][0]["rows"] == [["PLC 버전", "확인 중"]]
    first = wb.run(ws, "P-ASM-001", "2026-W41")
    assert first["status"] == "need_response" and first["response_name"] == "weekly_rollup__P-ASM-001__2026-W41.json"
    assert "D-261006-ljh-01" in first["prompt"] and "{{" not in first["prompt"]
    with pytest.raises(wb.WorkbenchError, match="JSON"):
        wb.save_response(ws, first["response_name"], "JSON 아님")
    weekly = {"headline": {"text": "금주(W41)에는 북미 적용 준비", "source_ids": ["D-261006-ljh-01"], "changed": True},
              "progress": [{"text": "북미 적용 준비 회의 진행", "source_ids": ["D-261006-ljh-01"], "changed": True}],
              "next_plan": [], "issues": [], "milestone_updates": []}
    wb.save_response(ws, first["response_name"], "```json\n" + json.dumps(weekly, ensure_ascii=False) + "\n```")
    second = wb.run(ws, "P-ASM-001", "2026-W41")
    assert second["status"] == "need_response" and second["prompt_id"] == "cumulative_update"
    prev = read(ws / "data/derived/cumulative/P-ASM-001/2026-W40.json") if (ws / "data/derived/cumulative/P-ASM-001/2026-W40.json").exists() else None
    cum = {"items": [{"text": "북미 적용 준비 회의 진행", "source_ids": ["D-261006-ljh-01"]}],
           "pinned_facts": (prev or {}).get("pinned_facts", []), "new_pinned_facts": []}
    wb.save_response(ws, second["response_name"], json.dumps(cum, ensure_ascii=False))
    third = wb.run(ws, "P-ASM-001", "2026-W41")
    assert third["status"] == "ok", third
    assert wb.clear_responses(ws, "P-ASM-001", "2026-W41") == [
        "cumulative_update__P-ASM-001__2026-W41.json", "weekly_rollup__P-ASM-001__2026-W41.json"]


def test_edit_and_delete_daily(ws):
    saved = wb.save_daily(ws, {"date": "2026-10-06", "author": "khw", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "첫 메모"})
    edited = wb.save_daily(ws, {"daily_id": saved["daily_id"], "date": "2026-10-06", "author": "khw", "visibility": "project",
                                "project_id": "P-ASM-001", "raw_text": "고친 메모"})
    assert edited["daily_id"] == saved["daily_id"] and edited["meta"]["revision"] == 2 and edited["raw_text"] == "고친 메모"
    wb.mark_deleted(ws, saved["daily_id"])
    assert wb.list_dailies(ws, "P-ASM-001", "2026-W41")[0]["excluded"] == "삭제됨"
    for bad in ({"author": "LJH"}, {"date": "10/06"}, {"raw_text": ""}, {"category": "XX"}, {"table_text": "a,b\n1"}):
        form = {"date": "2026-10-06", "author": "khw", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "x", **bad}
        with pytest.raises(wb.WorkbenchError):
            wb.save_daily(ws, form)


def test_files_stay_inside_workspace(ws):
    with pytest.raises(wb.WorkbenchError):
        wb.resolve_file(ws, "../../etc/passwd")
    with pytest.raises(wb.WorkbenchError):
        wb.save_response(ws, "../evil.json", "{}")


def test_http_smoke(ws):
    server = make_server(ws, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.status, res.read()
        assert b"<title>" in call("/")[1]
        assert json.loads(call("/api/projects")[1])["projects"][0]["project_id"] == "P-ASM-001"
        result = json.loads(call("/api/run", {"project_id": "P-ASM-001", "week": "2026-W40"})[1])
        assert result["status"] == "ok"
        status, data = call("/files/" + urllib.request.quote(result["files"]["pptx"]))
        assert status == 200 and data[:2] == b"PK"
        with pytest.raises(urllib.error.HTTPError) as info:
            call("/api/daily", {"date": "bad", "author": "ljh", "raw_text": "x"})
        assert info.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
