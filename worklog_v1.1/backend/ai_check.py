"""사내 AI(EXAONE) 연결 점검 (AI점검.bat). 요청 모양을 하나씩 바꿔 보내 HTTP 500 등의 원인을 좁힌다 (결정 I40).

config/config.json 의 AI_API_URL / AI_API_KEY / AI_MODEL 을 쓴다. 키와 주소의 쿼리 문자열은 출력하지 않는다.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import Settings, load_settings  # noqa: E402
from app.services.reports import failed_request_path  # noqa: E402
from weekly_report.ai import UrlLibTransport, _error_detail, _url_hint  # noqa: E402


class LegacyTransport:
    """예전 방식(2026-10-06 이전): Content-Type에 charset 없음, 한글을 UTF-8 원문 그대로, 요청 ID·Accept 없음, 기본 User-Agent."""

    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes:
        request = urllib.request.Request(url, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                         {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

SAMPLE = "재료교체 위치 불량 개선 로직을 3호기에 시험 적용해 불량률이 0.18%에서 0.15%로 감소했고, 원인 분석을 계속 진행했습니다. "
SYSTEM = "너는 업무 보고서 작성 보조다. 출력은 JSON만 쓴다."
ASK = '위 내용을 한 문장으로 요약해 {"items": [{"text": "..."}]} JSON으로만 답하세요.'


def _korean(chars: int) -> str:
    return (SAMPLE * (chars // len(SAMPLE) + 1))[:chars] + "\n\n" + ASK


def cases(model: str | None, saved: dict[str, Any] | None) -> list[tuple[str, str, dict[str, Any]]]:
    """(기호, 설명, 요청 본문). A2만 예전 방식(LegacyTransport)으로 보낸다."""
    def body(messages: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
        b: dict[str, Any] = {"messages": messages, **extra}
        if model:
            b["model"] = model
        return b

    user = lambda text: [{"role": "user", "content": text}]  # noqa: E731
    out = [
        ("A", "user 'hello'만 (이전에 성공한 모양)", body(user("hello"))),
        ("A2", "짧은 한글 — 예전 방식(charset 없음·UTF-8 원문·요청 ID 없음)", body(user("안녕하세요. 한 문장으로 답하세요."))),
        ("A3", "짧은 한글 — 지금 방식(charset=utf-8·ASCII JSON·요청 ID)", body(user("안녕하세요. 한 문장으로 답하세요."))),
        ("B", "A + temperature 0.1", body(user("hello"), temperature=0.1)),
        ("C", "system + user (짧게)", body([{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hello"}])),
        ("D", "user 한글 약 4,000자", body(user(_korean(4000)))),
        ("E", "user 한글 약 12,000자", body(user(_korean(12000)))),
        ("F", "user 한글 약 24,000자", body(user(_korean(24000)))),
    ]
    if saved and isinstance(saved.get("body"), dict):
        chars = sum(len(str(m.get("content", ""))) for m in saved["body"].get("messages", []))
        out.append(("G", f"마지막으로 실패한 실제 요청 다시 보내기 ({saved.get('promptId')}, {chars:,}자)", saved["body"]))
    return out


def send(transport: Any, url: str, key: str, body: dict[str, Any], timeout: float) -> tuple[str, float, str]:
    """(결과 'ok'|상태번호|오류 종류, 걸린 초, 응답 앞부분)"""
    started = time.monotonic()
    try:
        raw = transport.request(url, key, body, timeout)
        text = raw.decode("utf-8", "replace")
        try:
            message = json.loads(text)["choices"][0]["message"]
            text = (message.get("content") or "").strip() or f"(본문 없음, finish_reason={json.loads(text)['choices'][0].get('finish_reason')})"
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            pass
        return "ok", time.monotonic() - started, " ".join(text.split())[:200]
    except urllib.error.HTTPError as exc:
        return str(exc.code), time.monotonic() - started, _error_detail(exc, 200)
    except (TimeoutError, socket.timeout):
        return "timeout", time.monotonic() - started, f"{timeout:g}초 안에 응답 없음"
    except urllib.error.URLError as exc:
        return "connect", time.monotonic() - started, type(exc.reason).__name__


def conclude(results: dict[str, str]) -> list[str]:
    """결과 → 원인 추정과 조치."""
    ok = lambda k: results.get(k) == "ok"  # noqa: E731
    lines: list[str] = []
    if not ok("A"):
        return ["A(가장 단순한 요청)부터 실패: 주소(AI_API_URL 전체 경로)·키·모델명(AI_MODEL)을 확인하세요. 프로그램 문제가 아닙니다."]
    if "A2" in results and not ok("A2") and ok("A3"):
        lines.append("예전 방식의 한글 요청만 실패: 한글 인코딩(charset·UTF-8 원문)이나 요청 ID 헤더가 원인이었고, 지금 방식으로 해결됩니다.")
    if "A3" in results and not ok("A3"):
        lines.append("지금 방식의 짧은 한글 요청도 실패: 요청 ID 헤더 이름이 사내 문서와 다를 수 있습니다 → config.json 의 AI_REQUEST_ID_HEADER 를"
                     " 문서의 이름으로 바꾸거나 \"\" 로 비워 보세요.")
    if not ok("B") or not ok("C"):
        what = " · ".join(x for x, k in (("temperature", "B"), ("system 역할", "C")) if not ok(k))
        lines.append(f"게이트웨이가 {what}을(를) 처리하지 못함 → config.json 에 \"AI_COMPAT_MODE\": true 를 넣으세요"
                     " (기본 auto도 5xx가 계속되면 자동으로 이 형식으로 바꿔 다시 보냄).")
    sizes = [("D", 4000), ("E", 12000), ("F", 24000)]
    failed = [n for k, n in sizes if k in results and not ok(k)]
    if failed:
        passed = [n for k, n in sizes if ok(k)]
        limit = max(passed) if passed else 2000
        lines.append(f"입력 {min(failed):,}자부터 실패: 입력 길이 한도로 보입니다 → config.json 에 \"AI_INPUT_CHARS\": {max(limit * 2 // 3, 2000)} 정도를 넣으세요"
                     " (업무일지 원문을 그만큼으로 줄여 보냄).")
    if "G" in results and not ok("G") and not lines:
        lines.append("짧은 요청·긴 한글은 되는데 실제 요청만 실패: 결과 앞부분과 data/reports/ai_debug/last_failed_request.json"
                     " 의 promptId·글자 수를 개발 담당에게 알려 주세요 (키는 들어 있지 않음).")
    if any(v == "timeout" for v in results.values()):
        lines.append("시간 초과가 있음 → config.json 의 AI_TIMEOUT_SECONDS 를 늘리거나 AI_INPUT_CHARS 를 줄이세요.")
    return lines or ["모든 요청이 성공했습니다. 다시 보고자료를 만들어 보고, 실패하면 오류 메시지 전체를 알려 주세요."]


def run(settings: Settings, transport: Any = None, out: Callable[[str], None] = print, legacy: Any = None) -> list[str]:
    if not (settings.ai_api_url and settings.ai_api_key):
        out("config/config.json 에 AI_API_URL 과 AI_API_KEY 가 없습니다. 먼저 넣고 다시 실행하세요.")
        return []
    transport = transport or UrlLibTransport(settings.ai_request_id_header or None)
    legacy = legacy or LegacyTransport()
    saved_path = failed_request_path(settings)
    saved = None
    if saved_path.is_file():
        try:
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
        except ValueError:
            saved = None
    out(f"요청 주소: {_url_hint(settings.ai_api_url)} / 모델: {settings.ai_model or '(지정 안 함)'} / 제한 시간 {settings.ai_timeout_seconds:g}초"
        f" / 요청 ID 헤더: {settings.ai_request_id_header or '(보내지 않음)'}")
    out("-" * 70)
    results: dict[str, str] = {}
    for mark, label, body in cases(settings.ai_model, saved):
        out(f"[{mark}] {label} ...")
        sender = legacy if mark == "A2" else transport
        status, seconds, detail = send(sender, settings.ai_api_url, settings.ai_api_key, body, settings.ai_timeout_seconds)
        results[mark] = status
        rid = getattr(sender, "last_request_id", None) if mark != "A2" else None
        out(f"    → {'성공' if status == 'ok' else '실패 ' + status} ({seconds:.1f}초){f' 요청 ID {rid}' if rid else ''} {detail}")
    out("-" * 70)
    lines = conclude(results)
    for line in lines:
        out("결론: " + line)
    return lines


if __name__ == "__main__":
    run(load_settings())
