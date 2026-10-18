"""Instagram 웹훅 해석과 Send API (PRD 8.1).

페이로드 필드 이름은 [가설]이다. 1단계-B에서 실제 페이로드를 tests/fixtures에 넣고 확정한다.
해석 실패는 예외 대신 'unsupported'로 떨어뜨려 원본 payload를 보존한다.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

import httpx

REEL_ATTACHMENT_TYPES = {"ig_reel"}  # [가설] Meta 변경 이력 기준. 실제 타입은 1단계-B에서 확인


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass
class ReelAttachment:
    url: str
    video_id: str | None
    title: str | None


@dataclass
class IncomingMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    text: str | None
    reels: list[ReelAttachment] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)  # 첨부 type 목록
    raw: dict = field(default_factory=dict)


def parse_entries(body: dict) -> list[IncomingMessage]:
    """웹훅 본문 → 처리 대상 메시지. 에코·읽음·전달·반응 등 비대상 이벤트는 여기서 뺀다."""
    out: list[IncomingMessage] = []
    for entry in body.get("entry") or []:
        for ev in entry.get("messaging") or []:
            msg = ev.get("message")
            if not isinstance(msg, dict) or msg.get("is_echo") or msg.get("is_deleted"):
                continue
            mid = msg.get("mid")
            sender = (ev.get("sender") or {}).get("id")
            recipient = (ev.get("recipient") or {}).get("id")
            if not (mid and sender and recipient):
                continue
            m = IncomingMessage(mid, str(sender), str(recipient), msg.get("text"), raw=ev)
            for att in msg.get("attachments") or []:
                kind = att.get("type") or "unknown"
                payload = att.get("payload") or {}
                url = payload.get("url")
                if kind in REEL_ATTACHMENT_TYPES and url:
                    vid = payload.get("reel_video_id") or payload.get("video_id") or payload.get("id")
                    m.reels.append(ReelAttachment(url, str(vid) if vid else None, payload.get("title")))
                else:
                    m.unsupported.append(kind)
            out.append(m)
    return out


def classify(m: IncomingMessage) -> str:
    if m.reels:
        return "reel"
    if m.unsupported:
        return "unsupported"
    return "text"


def send_text(access_token: str, account_id: str, recipient_id: str, text: str,
              graph_version: str, client: httpx.Client | None = None) -> dict:
    """Send API. 24시간 응답 창 확인은 호출하는 쪽(워커)에서 한다. HUMAN_AGENT 태그는 쓰지 않는다."""
    url = f"https://graph.instagram.com/{graph_version}/{account_id}/messages"
    c = client or httpx.Client(timeout=15)
    try:
        r = c.post(url, json={"recipient": {"id": recipient_id}, "message": {"text": text}},
                   headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        return r.json()
    finally:
        if client is None:
            c.close()
