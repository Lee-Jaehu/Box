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
    c = client(Fake(503, 503, 503, 503))  # 3회 + 호환 형식 1회
    with pytest.raises(AIError) as err:
        call(c)
    assert "503" in str(err.value) and "요청 4회" in str(err.value) and "KEY" not in str(err.value)
    assert "입력 2자" in str(err.value) and "AI_INPUT_CHARS" in str(err.value)
    with pytest.raises(AIError) as err:  # 일시 오류가 아닌 것(404 등)은 바로 알린다
        call(client(Fake(404)))
    assert "404" in str(err.value) and "요청" not in str(err.value).split("—")[0]


class SystemRejecting(Fake):
    """system 역할이나 temperature가 있으면 500을 주는 게이트웨이 (사용자 PC에서 의심되는 경우)."""

    def __init__(self):
        super().__init__()

    def request(self, url, key, body, timeout):
        self.sent.append(body)
        if any(m["role"] == "system" for m in body["messages"]) or "temperature" in body:
            raise urllib.error.HTTPError(url, 500, "error", {}, io.BytesIO(b'{"description":"InternalServerError,Connection error."}'))
        return json.dumps(reply(json.dumps(ITEMS))).encode()


def test_compat_shape_after_persistent_5xx_then_kept_for_the_job():
    fake = SystemRejecting()
    c = client(fake, max_tokens=4000)
    assert c.complete("cumulative_update", "P", "W", "SYS", "USER") == ITEMS
    compat = fake.sent[-1]
    assert compat["messages"] == [{"role": "user", "content": "SYS\n\nUSER"}] and set(compat) == {"messages", "model"}
    assert len(fake.sent) == 4 and "호환 형식" in c.notes[-1]
    before = len(fake.sent)
    assert c.complete("cumulative_update", "P", "W", "SYS", "USER2") == ITEMS  # 같은 작업의 다음 호출은 처음부터 호환 형식
    assert len(fake.sent) == before + 1


def test_compat_can_be_forced_or_disabled():
    fake = SystemRejecting()
    c = client(fake)
    c.compat = True
    assert call(c) == ITEMS and len(fake.sent) == 1
    c = client(SystemRejecting())
    c.compat = False
    with pytest.raises(AIError):
        call(c)
    assert len(c.transport.sent) == 3


def test_config_ai_limits(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"AI_MAX_TOKENS": 8000, "AI_INPUT_CHARS": 10000}), encoding="utf-8")
    s = load_settings(cfg)
    assert (s.ai_max_tokens, s.ai_input_chars, s.ai_timeout_seconds) == (8000, 10000, 300.0)
    cfg.write_text(json.dumps({"AI_MAX_TOKENS": ""}), encoding="utf-8")
    assert load_settings(cfg).ai_max_tokens is None and load_settings(cfg).ai_compat_mode == "auto"
    for raw, want in ((True, "true"), ("false", "false"), ("auto", "auto")):
        cfg.write_text(json.dumps({"AI_COMPAT_MODE": raw}), encoding="utf-8")
        assert load_settings(cfg).ai_compat_mode == want


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


# ---------------------------------------------------------------- 실패 요청 저장 + AI점검 (결정 I40)

def test_failed_live_call_saves_request_without_key(tmp_path, monkeypatch):
    from app.services.reports import ServiceClient, failed_request_path

    monkeypatch.setattr(ai, "RETRY_DELAYS", (0.0, 0.0))
    settings = Settings(data_dir=tmp_path / "data", ai_api_url="https://ai.example/v1/chat/completions?token=QS", ai_api_key="SECRETKEY",
                        ai_model="k-exaone_v2")
    sc = ServiceClient(tmp_path / "ws", settings)
    sc.transport = Fake(500, 500, 500, 500)
    with pytest.raises(AIError):
        sc.complete("cumulative_update", "P", "2026-W40", "SYS", "USER")
    saved = failed_request_path(settings).read_text(encoding="utf-8")
    assert "SECRETKEY" not in saved and "QS" not in saved and "ai.example" not in saved
    data = json.loads(saved)
    assert data["promptId"] == "cumulative_update" and data["sends"] == 4 and data["compat"] is True
    assert data["body"]["messages"][0]["content"] == "SYS\n\nUSER"


def test_ai_check_concludes_cause(tmp_path):
    import ai_check
    from app.services.reports import _save_failed_request_file

    settings = Settings(data_dir=tmp_path / "data", ai_api_url="https://ai.example/v1/chat/completions?token=QS", ai_api_key="SECRETKEY",
                        ai_model="k-exaone_v2")

    class Gateway:
        """system·temperature 거절, 한글 1만 자 넘으면 500."""

        def request(self, url, key, body, timeout):
            chars = sum(len(m["content"]) for m in body["messages"])
            if any(m["role"] == "system" for m in body["messages"]) or "temperature" in body or chars > 10000:
                raise urllib.error.HTTPError(url, 500, "error", {}, io.BytesIO(b'{"description":"Connection error."}'))
            return json.dumps(reply("ok")).encode()

    _save_failed_request_file(settings, {"messages": [{"role": "user", "content": "x" * 30000}], "model": "k-exaone_v2"},
                              {"promptId": "weekly_rollup"})
    printed: list[str] = []
    lines = ai_check.run(settings, Gateway(), printed.append)
    text = "\n".join(printed)
    assert "SECRETKEY" not in text and "QS" not in text
    assert "[G]" in text and "weekly_rollup" in text
    assert any("temperature · system 역할" in x and "AI_COMPAT_MODE" in x for x in lines)
    assert any("12,000자부터 실패" in x and '"AI_INPUT_CHARS": 2666' in x for x in lines)
    assert ai_check.conclude({"A": "500"})[0].startswith("A(가장 단순한 요청)부터 실패")
    assert ai_check.conclude({k: "ok" for k in "ABCDEF"})[0].startswith("모든 요청이 성공")


# ---------------------------------------------------------------- 붙여넣기 방식이 되는 이유 (설정 없음)

def test_paste_mode_reason_names_file_and_empty_fields_without_key(tmp_path, monkeypatch):
    from app.services.reports import config_info

    for name in ("WORKLOG_AI_API_URL", "WORKLOG_AI_API_KEY", "WORKLOG_AI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    missing = load_settings(tmp_path / "없음.json")
    assert not missing.ai_live and "설정 파일이 없음" in missing.ai_paste_reason
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"AI_API_URL": "https://ai.example/v1/chat/completions", "AI_API_KEY": ""}), encoding="utf-8")
    info = config_info(load_settings(cfg))
    assert info["aiMode"] == "paste" and str(cfg) in info["aiPasteReason"] and "AI_API_KEY" in info["aiPasteReason"]
    assert "AI_API_URL" not in info["aiPasteReason"]
    monkeypatch.setenv("WORKLOG_AI_API_KEY", "SECRETKEY")  # 환경변수가 config.json보다 우선
    live = load_settings(cfg)
    assert live.ai_live and live.ai_paste_reason == "" and "SECRETKEY" not in json.dumps(config_info(live))
