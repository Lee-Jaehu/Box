"""카카오 OAuth·토큰 모의 테스트. 카카오 서버는 httpx.MockTransport로 대신한다."""

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from rsb import kakao
from rsb.app import create_app


class FakeKakao:
    def __init__(self, user_id=4242):
        self.user_id = user_id
        self.calls: list[tuple[str, dict]] = []
        self.refresh_response = {"access_token": "acc-2", "expires_in": 21599}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()} if request.content else {}
        self.calls.append((path, form))
        if path == "/oauth/token" and form.get("grant_type") == "authorization_code":
            return httpx.Response(200, json={"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 21599,
                                             "refresh_token_expires_in": 5183999, "token_type": "bearer"})
        if path == "/oauth/token" and form.get("grant_type") == "refresh_token":
            return httpx.Response(200, json=self.refresh_response)
        if path == "/v2/user/me":
            return httpx.Response(200, json={"id": self.user_id})
        if path == "/v2/api/talk/memo/default/send":
            return httpx.Response(200, json={"result_code": 0})
        return httpx.Response(404)


@pytest.fixture
def fake():
    return FakeKakao()


@pytest.fixture
def client(settings, fake):
    return TestClient(create_app(settings, httpx.Client(transport=httpx.MockTransport(fake))),
                      follow_redirects=False)


def login(client):
    r = client.get("/oauth/kakao/login")
    assert r.status_code == 302
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["scope"] == ["talk_message"] and q["client_id"] == ["kakao-key"]
    return q["state"][0]


def test_login_flow_stores_encrypted_tokens(client, conn, settings):
    state = login(client)
    r = client.get("/oauth/kakao/callback", params={"code": "c", "state": state})
    assert r.status_code == 200
    row = conn.execute("SELECT * FROM kakao_tokens").fetchone()
    assert row["kakao_user_id"] == "4242"
    assert "acc-1" not in row["access_token_enc"] and "ref-1" not in row["refresh_token_enc"]
    f = Fernet(settings.token_key.encode())
    assert f.decrypt(row["refresh_token_enc"].encode()) == b"ref-1"
    # 만료값은 응답의 expires_in 기준
    secs = conn.execute("SELECT extract(epoch FROM expires_at - now()) s FROM kakao_tokens").fetchone()["s"]
    assert 21500 < secs <= 21599


def test_state_is_required_and_single_use(client, conn):
    assert client.get("/oauth/kakao/callback", params={"code": "c", "state": "forged"}).status_code == 400
    state = login(client)
    assert client.get("/oauth/kakao/callback", params={"code": "c", "state": state}).status_code == 200
    assert client.get("/oauth/kakao/callback", params={"code": "c", "state": state}).status_code == 400


def test_expired_state_rejected(client, conn):
    state = login(client)
    conn.execute("UPDATE oauth_states SET expires_at = now() - interval '1 second'")
    conn.commit()
    assert client.get("/oauth/kakao/callback", params={"code": "c", "state": state}).status_code == 400


def test_other_kakao_user_rejected(client, conn, fake):
    fake.user_id = 1111
    state = login(client)
    r = client.get("/oauth/kakao/callback", params={"code": "c", "state": state})
    assert r.status_code == 403 and "user_not_allowed" in r.text
    assert conn.execute("SELECT count(*) n FROM kakao_tokens").fetchone()["n"] == 0


def test_test_send_requires_admin_and_sends(client, conn, fake):
    assert client.post("/admin/kakao/test-send").status_code == 401
    assert client.post("/admin/kakao/test-send", headers={"Authorization": "Bearer nope"}).status_code == 401
    state = login(client)
    client.get("/oauth/kakao/callback", params={"code": "c", "state": state})
    r = client.post("/admin/kakao/test-send", headers={"Authorization": "Bearer admin-secret"})
    assert r.status_code == 200 and r.json() == {"sent": True, "result_code": 0}
    path, form = fake.calls[-1]
    tpl = json.loads(form["template_object"])
    assert tpl["object_type"] == "text" and tpl["link"]["web_url"] == "https://rsb.test"


def test_refresh_keeps_old_refresh_token_when_absent(client, conn, settings, fake):
    state = login(client)
    client.get("/oauth/kakao/callback", params={"code": "c", "state": state})
    conn.execute("UPDATE kakao_tokens SET expires_at = now() + interval '1 minute'")
    conn.commit()
    http = httpx.Client(transport=httpx.MockTransport(fake))
    assert kakao.access_token(conn, settings, http) == "acc-2"
    conn.commit()
    f = Fernet(settings.token_key.encode())
    row = conn.execute("SELECT * FROM kakao_tokens").fetchone()
    assert f.decrypt(row["refresh_token_enc"].encode()) == b"ref-1"
    assert f.decrypt(row["access_token_enc"].encode()) == b"acc-2"
    # 새 리프레시 토큰이 오면 교체
    fake.refresh_response = {"access_token": "acc-3", "expires_in": 100, "refresh_token": "ref-2",
                             "refresh_token_expires_in": 5183999}
    conn.execute("UPDATE kakao_tokens SET expires_at = now()")
    conn.commit()
    assert kakao.access_token(conn, settings, http) == "acc-3"
    conn.commit()
    row = conn.execute("SELECT * FROM kakao_tokens").fetchone()
    assert f.decrypt(row["refresh_token_enc"].encode()) == b"ref-2"


def test_refresh_expired_requires_relogin(client, conn, settings, fake):
    state = login(client)
    client.get("/oauth/kakao/callback", params={"code": "c", "state": state})
    conn.execute("UPDATE kakao_tokens SET expires_at = now(), refresh_expires_at = now() - interval '1 second'")
    conn.commit()
    with pytest.raises(kakao.KakaoError, match="refresh_expired"):
        kakao.access_token(conn, settings, httpx.Client(transport=httpx.MockTransport(fake)))


def test_tokens_never_logged(client, conn, settings, fake, caplog):
    caplog.set_level("DEBUG")
    state = login(client)
    client.get("/oauth/kakao/callback", params={"code": "c", "state": state})
    conn.execute("UPDATE kakao_tokens SET expires_at = now()")
    conn.commit()
    kakao.access_token(conn, settings, httpx.Client(transport=httpx.MockTransport(fake)))
    for secret in ("acc-1", "ref-1", "acc-2"):
        assert secret not in caplog.text
