"""웹 테스트 화면: 작업공간 로직과 HTTP 스모크 테스트."""

import hashlib
import json
import shutil
from pathlib import Path
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
    wb.init_workspace(tmp_path / "ws")
    return tmp_path / "ws"


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


def test_reset_survives_locked_file_and_backs_up_user_data(ws, monkeypatch):
    """Windows처럼 열려 있는 파일을 지울 수 없어도 초기화는 끝까지 복원하고, 입력은 백업한다."""
    memo = wb.save_daily(ws, {"date": "2026-10-06", "author": "khw", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "백업될 메모"})
    assert wb.run(ws, "P-ASM-001", "2026-W40")["status"] == "ok"
    original_unlink = Path.unlink

    def locked_unlink(self, *args, **kwargs):
        if self.suffix in (".pptx", ".TTF"):
            raise PermissionError(13, "다른 프로세스가 사용 중", str(self))
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)
    result = wb.init_workspace(ws, force=True)
    monkeypatch.undo()
    assert "output/P-ASM-001_2026-W40.pptx" in result["locked"]
    assert wb.workspace_ok(ws) and (ws / "schemas/daily.schema.json").exists()
    assert not any(d["daily_id"] == memo["daily_id"] for d in wb.list_dailies(ws, "P-ASM-001", "2026-W41"))
    backup = Path(result["backup"])
    assert (backup / f"data/raw/daily/2026/26-10-06/{memo['daily_id']}.json").exists()
    assert wb.save_daily(ws, {"date": "2026-10-06", "author": "ljh", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "초기화 후 저장"})


def test_broken_workspace_is_repaired_without_touching_user_memos(ws):
    """초기화가 중간에 끊겨 schemas 등이 사라진 상태(사용자 보고 사례) → 다음 요청에서 빠진 파일만 복구."""
    memo = wb.save_daily(ws, {"date": "2026-09-28", "author": "ljh", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "사용자가 고친 메모"})
    shutil.rmtree(ws / "schemas")
    shutil.rmtree(ws / "config")
    assert not wb.workspace_ok(ws)
    server = make_server(ws, port=0)  # 서버 시작 시 복구
    server.server_close()
    assert wb.workspace_ok(ws)
    texts = {d["daily_id"]: d["raw_text"] for d in wb.list_dailies(ws, "P-ASM-001", "2026-W40")}
    assert texts[memo["daily_id"]] == "사용자가 고친 메모"
    assert wb.save_daily(ws, {"date": "2026-10-06", "author": "ljh", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "복구 후 저장"})


@pytest.mark.skipif(not Path("/proc/self/fd").exists(), reason="리눅스 /proc 필요")
def test_no_workspace_files_left_open_after_run(ws):
    import os

    assert wb.run(ws, "P-ASM-001", "2026-W40")["status"] == "ok"
    still_open = []
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if target.startswith(str(ws.resolve())):
            still_open.append(target)
    assert still_open == []


def test_backup_failure_aborts_reset_without_deleting(ws, monkeypatch):
    memo = wb.save_daily(ws, {"date": "2026-10-06", "author": "khw", "visibility": "project", "project_id": "P-ASM-001", "raw_text": "지켜야 할 메모"})

    def broken_copytree(src, dst, *args, **kwargs):
        raise OSError(28, "디스크 공간 부족")

    monkeypatch.setattr(wb.shutil, "copytree", broken_copytree)
    with pytest.raises(wb.WorkbenchError, match="백업에 실패해 초기화를 중단"):
        wb.init_workspace(ws, force=True)
    monkeypatch.undo()
    assert wb.workspace_ok(ws)
    assert any(d["daily_id"] == memo["daily_id"] for d in wb.list_dailies(ws, "P-ASM-001", "2026-W41"))


def test_each_reset_gets_its_own_backup(ws, monkeypatch):
    class FixedClock:
        @staticmethod
        def now(tz=None):
            from datetime import datetime as real

            return real(2026, 10, 4, 9, 0, 0, tzinfo=tz)

    monkeypatch.setattr(wb, "datetime", FixedClock)  # 같은 초에 두 번 초기화
    first = wb.init_workspace(ws, force=True)["backup"]
    second = wb.init_workspace(ws, force=True)["backup"]
    assert first != second and Path(first).exists() and Path(second).exists()


def test_any_missing_runtime_file_triggers_repair(ws):
    for rel in ("schemas/cumulative.schema.json", "schemas/project.schema.json", "prompts/fit_to_budget.user.txt"):
        (ws / rel).unlink()
        assert not wb.workspace_ok(ws) and rel in wb.missing_files(ws)
        wb.init_workspace(ws)
        assert wb.workspace_ok(ws)
    # 사용자가 지운 AI 응답은 '빠진 파일'이 아니다 → 복구 때 되살리지 않는다
    wb.clear_responses(ws, "P-ASM-001", "2026-W40")
    assert wb.workspace_ok(ws)
    assert not (ws / "prompts/mock_responses/weekly_rollup__P-ASM-001__2026-W40.json").exists()


def _w41_need_cumulative(ws):
    wb.save_daily(ws, {"date": "2026-10-06", "author": "ljh", "visibility": "project", "project_id": "P-ASM-001",
                       "raw_text": "북미 적용 준비 회의 진행."})
    first = wb.run(ws, "P-ASM-001", "2026-W41")
    weekly = {"headline": {"text": "금주(W41)에는 북미 적용 준비", "source_ids": ["D-261006-ljh-01"]},
              "progress": [{"text": "북미 적용 준비 회의 진행", "source_ids": ["D-261006-ljh-01"]}], "next_plan": [], "issues": []}
    wb.save_response(ws, first["response_name"], json.dumps(weekly, ensure_ascii=False))
    second = wb.run(ws, "P-ASM-001", "2026-W41")
    assert second["prompt_id"] == "cumulative_update" and '"items": [...]' in second["format"]
    return second


def test_pasted_ai_answer_with_prose_and_wrapper_is_accepted(ws):
    """사용자 보고: EXAONE 답을 붙여 넣고 실행 → 'cumulative_update 응답에 items 배열이 없음'."""
    need = _w41_need_cumulative(ws)
    answer = ("누적 요약을 갱신했습니다.\n\n```json\n" + json.dumps({"cumulative_update": {
        "items": ["북미 적용 준비 회의 진행"], "pinned_facts": [], "new_pinned_facts": []}}, ensure_ascii=False)
        + "\n```\n\n고정 사실은 변경하지 않았습니다.")
    wb.save_response(ws, need["response_name"], answer)
    result = wb.run(ws, "P-ASM-001", "2026-W41")
    assert result["status"] == "ok", result
    cum = read(ws / "data/derived/cumulative/P-ASM-001/2026-W41.json")
    assert cum["items"][0]["text"] == "북미 적용 준비 회의 진행" and cum["items"][0]["source_ids"] == []


def test_wrong_shape_answer_is_rejected_at_save_with_reason(ws):
    need = _w41_need_cumulative(ws)
    with pytest.raises(wb.WorkbenchError, match=r'"items" 배열이 필요합니다 \(받은 최상위 키: summary\)'):
        wb.save_response(ws, need["response_name"], json.dumps({"summary": "요약"}))
    with pytest.raises(wb.WorkbenchError, match="weekly_rollup"):  # 이전 단계 답을 다시 붙여 넣은 경우
        wb.save_response(ws, need["response_name"], json.dumps({"headline": {"text": "h", "source_ids": []}, "progress": []}))
    assert not (ws / "prompts/mock_responses" / need["response_name"]).exists()


def test_bad_stored_answer_reopens_paste_panel_instead_of_dead_end(ws):
    need = _w41_need_cumulative(ws)
    bad = json.dumps({"summary": "요약"})
    (ws / "prompts/mock_responses" / need["response_name"]).write_text(bad, encoding="utf-8")  # 이전 버전이 저장한 응답
    result = wb.run(ws, "P-ASM-001", "2026-W41")
    assert result["status"] == "need_response" and result["prompt_id"] == "cumulative_update"
    assert '"items" 배열이 필요합니다' in result["error"] and result["previous"] == bad and result["prompt"] == need["prompt"]
    assert (ws / "prompts/mock_responses/weekly_rollup__P-ASM-001__2026-W41.json").exists()  # 앞 단계 응답은 유지
    wb.save_response(ws, need["response_name"], json.dumps({"items": [{"text": "북미 적용 준비 회의 진행", "source_ids": ["D-261006-ljh-01"]}]}))
    assert wb.run(ws, "P-ASM-001", "2026-W41")["status"] == "ok"
