"""웹훅·카카오 OAuth·관리용 API (PRD 8장 1단계 범위)."""

from __future__ import annotations

import hmac
import json
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

from . import db, instagram, intake, kakao
from .config import Settings, get_settings

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, http_client: httpx.Client | None = None) -> FastAPI:
    s = settings or get_settings()
    app = FastAPI(title="rsb", docs_url=None, redoc_url=None, openapi_url=None)
    client = http_client or httpx.Client(timeout=15)

    def require_admin(authorization: str | None) -> None:
        token = (authorization or "").removeprefix("Bearer ")
        if not s.admin_token or not hmac.compare_digest(token, s.admin_token):
            raise HTTPException(401)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/webhook/instagram")
    def webhook_verify(mode: str = Query(alias="hub.mode", default=""),
                       token: str = Query(alias="hub.verify_token", default=""),
                       challenge: str = Query(alias="hub.challenge", default="")):
        if mode == "subscribe" and s.ig_verify_token and hmac.compare_digest(token, s.ig_verify_token):
            return PlainTextResponse(challenge)
        raise HTTPException(403)

    @app.post("/webhook/instagram")
    async def webhook_receive(request: Request,
                              x_hub_signature_256: str | None = Header(default=None)):
        body = await request.body()
        # 1. 서명 검증
        if not instagram.verify_signature(s.ig_app_secret, body, x_hub_signature_256):
            raise HTTPException(401)
        try:
            data = json.loads(body)
        except ValueError:
            raise HTTPException(400)
        # 3. 에코·비대상 이벤트는 parse 단계에서 빠진다
        messages = instagram.parse_entries(data)
        # 2·4·5. 수신 계정·송신자 확인 → 영구 저장 → 커밋. 실패 시 5xx로 재전달 유도
        try:
            with db.connect(s.database_url) as conn:
                for m in messages:
                    allowed = m.recipient_id == s.ig_account_id and m.sender_id in s.ig_allowed_senders
                    with conn.transaction():
                        intake.record_message(conn, m, allowed=allowed)
                    if not allowed:
                        log.info("message sender=%s recipient=%s stored as ignored", m.sender_id, m.recipient_id)
        except Exception:
            log.exception("webhook persist failed")
            return Response(status_code=503)
        # 6. 커밋 후 200
        return Response(status_code=200)

    @app.get("/oauth/kakao/login")
    def kakao_login():
        with db.connect(s.database_url) as conn:
            url = kakao.login_url(conn, s)
        return RedirectResponse(url, status_code=302)

    @app.get("/oauth/kakao/callback")
    def kakao_callback(code: str | None = None, state: str | None = None, error: str | None = None):
        with db.connect(s.database_url) as conn:
            if not kakao.consume_state(conn, state):
                conn.commit()
                raise HTTPException(400, "invalid state")
            conn.commit()
            if error or not code:
                raise HTTPException(400, f"kakao error: {error}")
            try:
                kakao.complete_login(conn, s, code, client)
            except kakao.KakaoError as e:
                raise HTTPException(403, str(e))
        return PlainTextResponse("카카오 연결 완료")

    @app.post("/admin/kakao/test-send")
    def kakao_test_send(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        link = s.public_base_url or "https://example.com"
        with db.connect(s.database_url) as conn:
            try:
                res = kakao.send_memo(conn, s, kakao.text_template("세컨브레인 테스트 발송입니다.", link), client)
            except kakao.KakaoError as e:
                raise HTTPException(502, str(e))
        return {"sent": True, "result_code": res.get("result_code")}

    return app
