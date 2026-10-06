"""PPT 추출 실패 원인별 회귀 테스트 (결정 I39): 사고 과정 섞임, 길이 한도 잘림, 게이트웨이 일시 오류, 입력량."""
import io
import json
import socket
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import weekly_report.ai as ai
from app.config import Settings, load_settings
from app.main import create_app
from app.services.reports import run_next
from weekly_report.ai import AIError, ChatCompletionsAdapter, ExaoneClient, parse_json_value

ITEMS = {"items": [{"text": "정리했습니다.", "source_ids": []}]}


def reply(content, finish="stop", reasoning=None):
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "reasoning": reasoning}}]}


class Fake:
    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def request(self, url, key, body, timeout):
        self.sent.append(body)
        answer = self.answers.pop(0)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(url, answer, "error", {}, io.BytesIO(b'{"description":"InternalServerError,Connection error."}'))
        if isinstance(answer, BaseException):
            raise answer
        return json.dumps(answer).encode()


def client(fake, **adapter):
    c = ExaoneClient(Path("."), "live", transport=fake, adapter=ChatCompletionsAdapter(**adapter),
                     api_url="https://ai.example/v1/chat/completions", api_key="KEY", model="k-exaone_v2")
    c.slept = []
    c.sleep = c.slept.append
    return c


def call(c):
    return c.complete("cumulative_update", "P", "2026-W40", "s", "u")


def test_think_block_with_braces_before_json():
    """원인 1: 첫 '{'가 사고 과정 안에 있으면 예전 코드는 2회 모두 실패했다."""
    text = '<think>\n{진행} 항목과 형식 {"items": ...} 을 생각한다\n</think>\n\n' + json.dumps(ITEMS, ensure_ascii=False)
    fake = Fake(reply(text))
    assert call(client(fake)) == ITEMS and len(fake.sent) == 1
    # 닫히지 않은 <think> 뒤만 있는 경우·설명 문장 속 { } 뒤의 진짜 JSON도 찾는다
    assert parse_json_value('예시 {형식} 입니다. 결과: ' + json.dumps(ITEMS), "cumulative_update") == ITEMS
    with pytest.raises(json.JSONDecodeError):
        parse_json_value("<think>생각만 하다 끝남 {", "cumulative_update")
    # 형식이 틀린 JSON 안쪽 조각(["A"] → items로 보일 수 있음)을 답으로 고르지 않는다: 틀린 형식은 그대로 알려야 함
    assert parse_json_value('{"summary": ["A"], "pinned_facts": []}', "cumulative_update") == {"summary": ["A"], "pinned_facts": []}


def test_empty_content_reads_reasoning_json():
    c = client(Fake(reply("", reasoning="정리하면 " + json.dumps(ITEMS))))
    assert call(c) == ITEMS and "reasoning" in c.notes[0]


def test_length_cut_gives_clear_message_without_useless_retry():
    """원인 2: 사고 과정이 토큰을 다 써서 본문이 비면(finish_reason=length) 원인을 알려 준다. 같은 요청 재전송은 하지 않는다."""
    fake = Fake(reply(None, finish="length", reasoning="생각 " * 100))
    with pytest.raises(AIError) as err:
        call(client(fake))
    assert "길이 한도" in str(err.value) and "AI_MAX_TOKENS" in str(err.value) and len(fake.sent) == 1


def test_max_tokens_is_sent_only_when_set():
    fake = Fake(reply(json.dumps(ITEMS)), reply(json.dumps(ITEMS)))
    call(client(fake))
    call(client(fake, max_tokens=8000))
    assert "max_tokens" not in fake.sent[0] and fake.sent[1]["max_tokens"] == 8000


@pytest.mark.parametrize("error", [500, 502, 429, socket.timeout(), urllib.error.URLError(ConnectionResetError())])
def test_transient_errors_are_retried_with_wait(error):
    """원인 3: 게이트웨이 일시 오류 한 번에 job 전체가 실패하던 것을 대기 후 재요청."""
    c = client(Fake(error, reply(json.dumps(ITEMS))))
    assert call(c) == ITEMS
    assert c.slept == [ai.RETRY_DELAYS[0]] and c.call_log[-1]["sends"] == 2 and "다시 요청" in c.notes[0]


def test_transient_errors_give_up_with_count_and_no_secret():
    c = client(Fake(503, 503, 503))
    with pytest.raises(AIError) as err:
        call(c)
    assert "503" in str(err.value) and "요청 3회" in str(err.value) and "KEY" not in str(err.value)
    with pytest.raises(AIError) as err:  # 일시 오류가 아닌 것(404 등)은 바로 알린다
        call(client(Fake(404)))
    assert "404" in str(err.value) and "요청" not in str(err.value).split("—")[0]


def test_config_ai_limits(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"AI_MAX_TOKENS": 8000, "AI_INPUT_CHARS": 10000}), encoding="utf-8")
    s = load_settings(cfg)
    assert (s.ai_max_tokens, s.ai_input_chars, s.ai_timeout_seconds) == (8000, 10000, 300.0)
    cfg.write_text(json.dumps({"AI_MAX_TOKENS": ""}), encoding="utf-8")
    assert load_settings(cfg).ai_max_tokens is None


# ---------------------------------------------------------------- 서비스 job (서버 AI, 가짜 EXAONE)

def test_live_job_with_sectioned_tasks_survives_think_and_gateway_error(tmp_path, monkeypatch):
    from test_reports_team import Api, _answer

    sent: list[dict] = []

    def fake_request(self, url, key, body, timeout):
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        kind = ("weekly_rollup" if '"headline"' in system else "project_summary" if '"category"' in system else "cumulative_update")
        sent.append({"kind": kind, "user": user})
        if len(sent) == 2:  # 두 번째 요청은 게이트웨이 500
            raise urllib.error.HTTPError(url, 500, "error", {}, io.BytesIO(b"{}"))
        answer = json.dumps(_answer({"promptId": kind, "prompt": system + "\n" + user}), ensure_ascii=False)
        return json.dumps(reply("<think>{생각}</think>\n\n" + answer, reasoning="...")).encode()

    monkeypatch.setattr(ai.UrlLibTransport, "request", fake_request)
    monkeypatch.setattr(ai, "RETRY_DELAYS", (0.0, 0.0))
    settings = Settings(data_dir=tmp_path / "data", export_worker_enabled=False, report_worker_enabled=False,
                        ai_api_url="https://ai.example/v1/chat/completions", ai_api_key="K", ai_model="k-exaone_v2")
    with TestClient(create_app(settings)) as c:
        api = Api(c)
        division = api.post("/organizations", {"name": "담당", "kind": "division"}, actor=False)
        team = api.post("/organizations", {"name": "자동보정팀", "kind": "team", "parentId": division["id"]}, actor=False)
        user = api.post("/users", {"name": "홍길동", "teamId": team["id"], "employeeNumber": "E001"}, actor=False)
        api.actor = user["id"]
        project = api.post("/projects", {"name": "재료교체 불량 개선", "teamId": team["id"], "ownerUserId": user["id"], "status": "in_progress"})
        ms = api.post(f"/projects/{project['id']}/milestones", {"name": "로직 개발", "plannedStart": "2026-09-01", "plannedEnd": "2026-10-31"})
        body = [{"type": "paragraph", "content": [{"type": "text", "text": t}]}
                for t in ("## 진행 현황 : 불량률 0.18%에서 0.15%로 감소", "## 이슈 : 3호기 센서 오검출", "## 향후계획 : 10/8 확대 적용")]
        api.put(f"/projects/{project['id']}/logs/2026-09-30/{user['id']}", {"expectedRevision": 0, "tasks": [
            {"milestoneId": ms["id"], "content": {"documentVersion": 1, "format": "tiptap-json", "doc": {"type": "doc", "content": body}}}]})
        job = api.post("/reports/jobs", {"kind": "weekly", "template": "weekly", "week": "2026-W40", "projectIds": [project["id"]],
                                         "includeTeamSummary": True})
        run_next(c.app.state.rt)
        done = c.get(f"/api/v1/reports/jobs/{job['id']}").json()["data"]
        assert done["status"] == "succeeded", done.get("error")
        check = [f for f in done["result"]["files"] if f["label"] == "검사 보고서"][0]
        report = c.get(f"/api/v1/reports/jobs/{job['id']}/files/{check['name']}").text
    weekly_user = sent[0]["user"]
    assert "[진행 현황] 불량률 0.18%에서 0.15%로 감소" in weekly_user and "[이슈] 3호기 센서 오검출" in weekly_user
    assert "## 이슈" not in weekly_user  # 섹션 표시는 정리된 형태로
    assert [s["kind"] for s in sent] == ["weekly_rollup", "cumulative_update", "cumulative_update", "project_summary"]
    assert "누적 요약: HTTP 500 → 0초 뒤 다시 요청" in report  # 자동 조치가 검사 보고서에 남는다
    assert "입력" in report and "요청 2회" in report
