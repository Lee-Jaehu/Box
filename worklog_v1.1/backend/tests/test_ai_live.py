"""사내 EXAONE 호출 형식: JSON 강제 옵션(response_format) 기본 끔, 거절 시 옵션 없이 재요청, 오류 메시지에 서버 응답 포함."""
import io
import json
import urllib.error
from pathlib import Path

import pytest

from app.config import load_settings
from weekly_report.ai import AIError, ChatCompletionsAdapter, ExaoneClient

OK = {"choices": [{"message": {"content": '\n\n```json\n{"items": [{"text": "정리했습니다.", "source_ids": []}]}\n```',
                               "reasoning": "생각 과정"}}], "model": "k-exaone_v2"}


class FakeTransport:
    """보낸 요청을 기록하고, 정해 둔 응답(바이트) 또는 HTTP 오류를 차례로 돌려준다."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def request(self, url, key, body, timeout):
        self.sent.append(body)
        answer = self.answers.pop(0)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(url, answer, "error", {}, io.BytesIO(
                json.dumps({"result_code": answer, "description": "InternalServerError,Connection error."}).encode()))
        return json.dumps(answer).encode()


def client(transport, json_mode=False):
    c = ExaoneClient(Path("."), "live", transport=transport, adapter=ChatCompletionsAdapter(json_mode=json_mode),
                     api_url="https://ai.example/v1/chat/completions?token=secret", api_key="KEY", model="k-exaone_v2")
    c.sleep = lambda seconds: None  # 일시 오류 재요청 대기 없이
    return c


def test_default_request_has_no_json_mode_and_reads_fenced_json():
    t = FakeTransport(OK)
    payload = client(t).complete("cumulative_update", "P", "2026-W40", "system", "user")
    assert payload["items"][0]["text"] == "정리했습니다."
    assert "response_format" not in t.sent[0] and t.sent[0]["model"] == "k-exaone_v2"


def test_json_mode_rejected_retries_without_it():
    t = FakeTransport(500, OK)
    c = client(t, json_mode=True)
    assert c.complete("cumulative_update", "P", "2026-W40", "s", "u")["items"]
    assert "response_format" in t.sent[0] and "response_format" not in t.sent[1]
    assert "JSON 강제 옵션을 거절(HTTP 500)" in c.notes[0]


def test_http_error_message_shows_server_reply_without_key_or_query():
    with pytest.raises(AIError) as err:
        client(FakeTransport(500, 500, 500, 500)).complete("cumulative_update", "P", "2026-W40", "s", "u")  # 3회 + 호환 형식 1회
    msg = str(err.value)
    assert "HTTP 오류: 500" in msg and "요청 4회" in msg and "AI점검.bat" in msg and "Connection error" in msg and "https://ai.example/v1/chat/completions" in msg
    assert "secret" not in msg and "KEY" not in msg


def test_config_ai_json_mode(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"AI_JSON_MODE": True}), encoding="utf-8")
    assert load_settings(cfg).ai_json_mode is True
    cfg.write_text("{}", encoding="utf-8")
    assert load_settings(cfg).ai_json_mode is False
