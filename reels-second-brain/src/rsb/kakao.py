"""카카오 OAuth·토큰·나에게 보내기 (PRD 8.2, 10장).

토큰은 암호화 저장하고 로그에 남기지 않는다. 만료값은 응답의 expires_in을 그대로 쓴다.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import psycopg
from cryptography.fernet import Fernet

from .config import Settings

log = logging.getLogger(__name__)

AUTH_HOST = "https://kauth.kakao.com"
API_HOST = "https://kapi.kakao.com"
STATE_TTL = timedelta(minutes=10)
REFRESH_MARGIN = timedelta(minutes=5)


class KakaoError(Exception):
    pass


def _fernet(s: Settings) -> Fernet:
    if not s.token_key:
        raise KakaoError("RSB_TOKEN_KEY가 설정되지 않았습니다")
    return Fernet(s.token_key.encode())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def login_url(conn: psycopg.Connection, s: Settings) -> str:
    state = secrets.token_urlsafe(24)
    conn.execute("DELETE FROM oauth_states WHERE expires_at < now()")
    conn.execute("INSERT INTO oauth_states (state, expires_at) VALUES (%s, %s)", (state, _now() + STATE_TTL))
    q = urlencode({"client_id": s.kakao_rest_api_key, "redirect_uri": s.kakao_redirect_uri,
                   "response_type": "code", "state": state, "scope": "talk_message"})
    return f"{AUTH_HOST}/oauth/authorize?{q}"


def consume_state(conn: psycopg.Connection, state: str | None) -> bool:
    if not state:
        return False
    row = conn.execute("DELETE FROM oauth_states WHERE state=%s RETURNING expires_at", (state,)).fetchone()
    return bool(row and row["expires_at"] > _now())


def _token_request(client: httpx.Client, s: Settings, data: dict) -> dict:
    data = {"client_id": s.kakao_rest_api_key, **data}
    if s.kakao_client_secret:
        data["client_secret"] = s.kakao_client_secret
    r = client.post(f"{AUTH_HOST}/oauth/token", data=data)
    if r.status_code != 200:
        # 응답 본문에 토큰이 없을 때만 오류 코드를 남긴다
        raise KakaoError(f"token_http_{r.status_code}:{_error_code(r)}")
    return r.json()


def _error_code(r: httpx.Response) -> str:
    try:
        j = r.json()
        return str(j.get("error_code") or j.get("error") or j.get("code") or "")
    except ValueError:
        return ""


def complete_login(conn: psycopg.Connection, s: Settings, code: str, client: httpx.Client) -> str:
    """코드 → 토큰 → 사용자 확인 → 암호화 저장. 연결된 카카오 사용자 ID를 반환."""
    tok = _token_request(client, s, {"grant_type": "authorization_code", "code": code,
                                     "redirect_uri": s.kakao_redirect_uri})
    me = client.get(f"{API_HOST}/v2/user/me", headers={"Authorization": f"Bearer {tok['access_token']}"})
    if me.status_code != 200:
        raise KakaoError(f"user_me_http_{me.status_code}")
    user_id = str(me.json()["id"])
    if not s.kakao_allowed_user_id:
        raise KakaoError(f"not_configured: KAKAO_ALLOWED_USER_ID={user_id} 로 설정한 뒤 다시 로그인하세요")
    if user_id != s.kakao_allowed_user_id:
        raise KakaoError("user_not_allowed")
    if "refresh_token" not in tok:
        raise KakaoError("no_refresh_token")
    _save(conn, s, user_id, tok, keep_refresh=None)
    return user_id


def _save(conn: psycopg.Connection, s: Settings, user_id: str, tok: dict, keep_refresh: str | None) -> None:
    f = _fernet(s)
    now = _now()
    refresh = tok.get("refresh_token")
    refresh_enc = f.encrypt(refresh.encode()).decode() if refresh else keep_refresh
    refresh_exp = now + timedelta(seconds=tok["refresh_token_expires_in"]) if "refresh_token_expires_in" in tok else None
    conn.execute(
        """INSERT INTO kakao_tokens (kakao_user_id, access_token_enc, refresh_token_enc, expires_at, refresh_expires_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, now())
           ON CONFLICT (kakao_user_id) DO UPDATE SET
             access_token_enc=EXCLUDED.access_token_enc,
             refresh_token_enc=EXCLUDED.refresh_token_enc,
             expires_at=EXCLUDED.expires_at,
             refresh_expires_at=coalesce(EXCLUDED.refresh_expires_at, kakao_tokens.refresh_expires_at),
             updated_at=now()""",
        (user_id, f.encrypt(tok["access_token"].encode()).decode(), refresh_enc,
         now + timedelta(seconds=tok["expires_in"]), refresh_exp),
    )


def access_token(conn: psycopg.Connection, s: Settings, client: httpx.Client) -> str:
    """유효한 액세스 토큰. 만료 임박이면 갱신한다. 행 잠금으로 갱신 동시 실행을 막는다."""
    f = _fernet(s)
    with conn.transaction():
        row = conn.execute(
            "SELECT * FROM kakao_tokens WHERE kakao_user_id=%s FOR UPDATE", (s.kakao_allowed_user_id,)
        ).fetchone()
        if row is None:
            raise KakaoError("not_linked")
        if row["expires_at"] - REFRESH_MARGIN > _now():
            return f.decrypt(row["access_token_enc"].encode()).decode()
        if row["refresh_expires_at"] and row["refresh_expires_at"] <= _now():
            raise KakaoError("refresh_expired: 카카오 로그인을 다시 하세요")
        refresh = f.decrypt(row["refresh_token_enc"].encode()).decode()
        tok = _token_request(client, s, {"grant_type": "refresh_token", "refresh_token": refresh})
        # 새 리프레시 토큰이 없으면 기존 값을 유지한다
        _save(conn, s, row["kakao_user_id"], tok, keep_refresh=row["refresh_token_enc"])
        log.info("kakao token refreshed (new refresh token: %s)", "refresh_token" in tok)
        return tok["access_token"]


def send_memo(conn: psycopg.Connection, s: Settings, template: dict, client: httpx.Client) -> dict:
    token = access_token(conn, s, client)
    r = client.post(f"{API_HOST}/v2/api/talk/memo/default/send",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"template_object": json.dumps(template, ensure_ascii=False)})
    if r.status_code != 200:
        raise KakaoError(f"memo_http_{r.status_code}:{_error_code(r)}")
    return r.json()


def text_template(text: str, link_url: str) -> dict:
    return {"object_type": "text", "text": text[:200],
            "link": {"web_url": link_url, "mobile_web_url": link_url}, "button_title": "전체 보기"}
