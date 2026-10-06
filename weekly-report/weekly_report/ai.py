"""EXAONE 클라이언트.

- mock(기본): prompts/mock_responses/{prompt_id}__{project_id}__{week}[__{variant}].json 을 응답으로 사용
- live: EXAONE_API_URL / EXAONE_API_KEY (선택: EXAONE_MODEL) 사용.
  요청·응답 변환은 Adapter로 분리했다. 실제 사내 API 계약은 확인되지 않았으므로
  현재 어댑터(Chat Completions 형식)는 "미검증"이다.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Protocol

RETRY_MESSAGE = "직전 응답이 JSON 형식이 아닙니다. 같은 내용을 JSON으로만 다시 출력하세요."


class AIError(RuntimeError):
    """AI 호출 실패 (키·원문은 메시지에 넣지 않는다)."""


class MockResponseMissing(AIError):
    """mock 응답 파일 없음."""


class Transport(Protocol):
    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes: ...


REQUEST_ID_HEADER = "X-Request-ID"
USER_AGENT = "Worklog-PPT/1.0"


class UrlLibTransport:
    """EXAONE API 문서의 "JSON 형식 요청" 규칙: Authorization Bearer 키 + 요청 ID 헤더, accept */*,
    Content-Type application/json; charset=utf-8. 본문은 ASCII JSON(한글은 \\uXXXX)으로 보내 문자 인코딩 해석과 무관하게 한다.
    요청 ID 헤더 이름은 설정(EXAONE_REQUEST_ID_HEADER)으로 바꾸거나 비워서 뺄 수 있다."""

    def __init__(self, request_id_header: str | None = REQUEST_ID_HEADER):
        self.request_id_header = request_id_header
        self.last_request_id: str | None = None

    def headers(self, key: str) -> dict[str, str]:
        self.last_request_id = str(uuid.uuid4())
        headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "*/*", "User-Agent": USER_AGENT,
                   "Authorization": f"Bearer {key}"}
        if self.request_id_header:
            headers[self.request_id_header] = self.last_request_id
        return headers

    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes:
        request = urllib.request.Request(url, json.dumps(body, ensure_ascii=True).encode("ascii"), self.headers(key), method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()


class Adapter(Protocol):
    """사내 API 계약이 정해지면 이 인터페이스만 새로 구현한다."""

    def build_request(self, messages: list[dict[str, str]], model: str | None) -> dict[str, Any]: ...

    def extract_text(self, raw: dict[str, Any]) -> str: ...


class ChatCompletionsAdapter:
    """OpenAI 호환 Chat Completions 형식 (미검증 가정)."""

    # 사내 EXAONE(k-exaone_v2) 게이트웨이는 response_format={"type":"json_object"}에 500을 돌려준다(2026-10-06 확인).
    # 기본은 붙이지 않는다. 프롬프트가 JSON만 요구하고 read_payload가 설명 문장·```json 표시를 걸러 JSON만 읽는다.
    def __init__(self, json_mode: bool = False, max_tokens: int | None = None):
        self.json_mode = json_mode
        self.max_tokens = max_tokens  # 지정할 때만 보낸다 (EXAONE_MAX_TOKENS)

    def build_request(self, messages: list[dict[str, str]], model: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"messages": messages, "temperature": 0.1}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.max_tokens:
            body["max_tokens"] = int(self.max_tokens)
        if model:
            body["model"] = model
        return body

    def extract_text(self, raw: dict[str, Any]) -> str:
        return self.extract(raw).text

    def extract(self, raw: dict[str, Any]) -> "Reply":
        """본문 + 끝난 이유(finish_reason) + 사고 과정(reasoning, 사고형 모델이 따로 줄 때)."""
        if isinstance(raw.get("content"), str):
            return Reply(raw["content"], raw.get("finish_reason"), None)
        choice = raw["choices"][0]
        message = choice.get("message") or {}
        reasoning = message.get("reasoning") or message.get("reasoning_content")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise TypeError("message.content가 문자열이 아님")
        return Reply(content or "", choice.get("finish_reason"), reasoning if isinstance(reasoning, str) else None)


class Reply:
    """AI 응답 한 건 (본문·끝난 이유·사고 과정)."""

    def __init__(self, text: str, finish_reason: str | None, reasoning: str | None):
        self.text, self.finish_reason, self.reasoning = text, finish_reason, reasoning


# 프롬프트별 응답 형식: 필수 배열 키, 반드시 객체여야 하는 키, 선택 배열 키
RESPONSE_SHAPES: dict[str, dict[str, tuple[str, ...]]] = {
    "weekly_rollup": {"objects": ("headline",), "lists": (), "optional": ("progress", "next_plan", "issues", "milestone_updates")},
    "cumulative_update": {"objects": (), "lists": ("items",), "optional": ("pinned_facts", "new_pinned_facts")},
    "fit_to_budget": {"objects": (), "lists": ("items",), "optional": ("dropped",)},
    # 팀 요약 페이지: items[].category/details는 summary.build_items가 확인
    "project_summary": {"objects": (), "lists": ("items",), "optional": ()},
    # 보고 자료: 필수 칸만 여기서 확인하고, 나머지 칸은 report.checks가 스키마·칸 단위 대체로 처리
    "report_monthly": {"objects": ("head_message",), "lists": ("project_comments",),
                       "optional": ("highlights", "risks", "requests")},
    "report_exec_summary": {"objects": ("title", "head_message"), "lists": ("background_conclusion",),
                            "optional": ("left_items", "right_items", "emphasis")},
}
# AI가 문장 앞뒤에 옮겨 쓴 근거 표시: "(P-ASM-001) ...", "(D-260922-ljh-01, D-...) ...", "... [근거: D-...]"
_ID = r"(?:D|CP|R)-\d{6}-[A-Za-z0-9]+(?:-\d+)?|P-[A-Z]+-\d{3}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
LEADING_IDS_RE = re.compile(rf"^\s*[(\[]\s*((?:{_ID})(?:\s*[,·/]\s*(?:{_ID}))*)\s*[)\]]\s*")
TRAILING_SOURCE_RE = re.compile(r"\s*\[근거:[^\]]*\]\s*$")
ID_RE = re.compile(_ID)
ITEM_LISTS = {"progress", "next_plan", "issues", "items", "pinned_facts", "new_pinned_facts", "dropped",
              "project_comments", "highlights", "risks", "requests", "background_conclusion", "left_items", "right_items"}
ITEM_OBJECTS = {"headline", "head_message", "title", "left_title", "right_title"}


class LengthExceeded(Exception):
    """응답이 길이 한도(finish_reason=length)로 잘려 JSON을 읽을 수 없음."""


PROMPT_LABELS = {"weekly_rollup": "주간 정리", "period_rollup": "기간 정리", "cumulative_update": "누적 요약",
                 "fit_to_budget": "분량 줄이기", "project_summary": "팀장 요약"}


def prompt_label(prompt_id: str) -> str:
    return PROMPT_LABELS.get(prompt_id, prompt_id)


class ResponseFormatError(AIError):
    """AI 응답이 JSON이지만 프롬프트가 요구한 형식이 아님."""

    def __init__(self, prompt_id: str, message: str):
        super().__init__(f"{prompt_id} 응답 형식 오류: {message}")
        self.prompt_id = prompt_id


# 사고형 모델이 본문에 섞어 보내는 사고 과정 (<think>…</think>). 안의 { } 때문에 JSON 찾기가 어긋난다.
_THINK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
_THINK_OPEN_RE = re.compile(r"<(think|thinking|reasoning)>.*", re.S | re.I)
MAX_JSON_STARTS = 400  # {·[ 위치를 이만큼까지 차례로 시도


def strip_reasoning(text: str) -> str:
    """<think>…</think> 구간을 뺀다. 닫히지 않은 것(잘린 응답)은 그 뒤를 모두 뺀다."""
    text = _THINK_RE.sub("", text)
    return _THINK_OPEN_RE.sub("", text)


def _json_values(text: str):
    """응답 원문(사고 과정을 뺀 본문)에서 읽히는 JSON 값을 차례로 내놓는다.
    전체가 JSON이면 그것 하나만. 아니면 ```json 블록 → 본문의 {·[ 위치마다 (읽힌 JSON 안쪽 위치는 건너뜀: 안쪽 조각을 답으로 고르지 않게)."""
    decoder = json.JSONDecoder()
    cleaned = strip_reasoning(text.strip().lstrip("\ufeff")).strip()
    try:
        yield json.loads(cleaned)
        return
    except json.JSONDecodeError:
        pass
    blocks = [m.group(1) for m in re.finditer(r"```[A-Za-z]*\s*\n?(.*?)```", cleaned, re.S)]
    if cleaned.startswith("```"):  # 닫는 ``` 없이 잘린 경우
        blocks.append(cleaned.split("\n", 1)[1] if "\n" in cleaned else "")
    for block in blocks:
        try:
            yield json.loads(block.strip())
        except json.JSONDecodeError:
            pass
    pos, tried = 0, 0
    while tried < MAX_JSON_STARTS:
        match = re.compile(r"[{\[]").search(cleaned, pos)
        if not match:
            return
        tried += 1
        try:
            value, end = decoder.raw_decode(cleaned, match.start())  # JSON 뒤에 설명 문장이 붙어도 된다
        except json.JSONDecodeError:
            pos = match.start() + 1
            continue
        yield value
        pos = end


def parse_json_value(text: str, prompt_id: str | None = None) -> Any:
    """설명 문장·```json 표시·사고 과정이 섞여 있어도 JSON 객체(또는 배열)를 꺼낸다.
    prompt_id를 주면 그 프롬프트의 응답 형식에 맞는 첫 값을, 없으면 처음 읽힌 값을 고른다."""
    shape = RESPONSE_SHAPES.get(prompt_id or "")
    first: Any = None
    found = False
    for value in _json_values(text):
        if shape is None or _has_shape(normalize_payload(value, prompt_id), shape):
            return value
        if not found:
            first, found = value, True
    if found:
        return first
    raise json.JSONDecodeError("JSON 없음", text, 0)


def parse_json_text(text: str) -> dict[str, Any]:
    """응답 원문 → JSON 객체."""
    value = parse_json_value(text)
    if not isinstance(value, dict):
        raise json.JSONDecodeError("JSON 객체가 아님", text, 0)
    return value


def _has_shape(value: Any, shape: dict[str, tuple[str, ...]]) -> bool:
    return isinstance(value, dict) and all(k in value for k in shape["objects"] + shape["lists"])


def strip_source_tags(item: Any) -> Any:
    """문장에 섞여 들어온 근거 ID 표시를 떼어 source_ids로 옮긴다 (PPT에 ID가 보이지 않게)."""
    if not isinstance(item, dict) or not isinstance(item.get("text"), str):
        return item
    text = TRAILING_SOURCE_RE.sub("", item["text"])
    match = LEADING_IDS_RE.match(text)
    ids: list[str] = []
    if match:
        ids = ID_RE.findall(match.group(1))
        text = text[match.end():]
    if text == item["text"]:
        return item
    sources = item.get("source_ids")
    if isinstance(sources, list) and all(isinstance(s, str) for s in sources):
        sources = list(dict.fromkeys([*sources, *ids]))
    return {**item, "text": text.strip(), "source_ids": sources if sources is not None else ids}


def normalize_payload(value: Any, prompt_id: str) -> Any:
    """흔한 변형을 받아들인다: 한 겹 감싼 객체, items 배열만 준 경우, 문자열 항목."""
    shape = RESPONSE_SHAPES.get(prompt_id)
    if shape is None:
        return value
    if isinstance(value, list) and shape["lists"] == ("items",):
        value = {"items": value}
    if isinstance(value, dict) and not _has_shape(value, shape):
        inner = [v for v in value.values() if _has_shape(v, shape)]
        if len(inner) == 1:  # {"result": {...}}, {"cumulative_update": {...}} 등
            value = inner[0]
    if isinstance(value, dict):
        value = dict(value)
        for key in ITEM_LISTS & set(value):
            if isinstance(value[key], list):
                value[key] = [strip_source_tags({"text": v, "source_ids": []} if isinstance(v, str) else v) for v in value[key]]
        for key in ITEM_OBJECTS & set(value):
            if isinstance(value[key], str) and key in shape["objects"] + ("headline", "left_title", "right_title"):
                value[key] = {"text": value[key], "source_ids": []}
            if isinstance(value[key], dict):
                value[key] = strip_source_tags(value[key])
    return value


def check_payload(value: Any, prompt_id: str) -> None:
    """프롬프트가 요구한 형식인지 확인한다. 틀리면 ResponseFormatError (어디가 틀렸는지 안내)."""
    shape = RESPONSE_SHAPES.get(prompt_id)
    if shape is None:
        return
    if not isinstance(value, dict):
        raise ResponseFormatError(prompt_id, f"JSON 객체({{...}})가 필요합니다 (받은 값: {type(value).__name__})")
    found = ", ".join(value) or "없음"
    if prompt_id != "weekly_rollup" and "headline" in value and "items" not in value:
        raise ResponseFormatError(prompt_id, "주간 정리(weekly_rollup) 응답으로 보입니다. 이 단계의 프롬프트를 AI에 보내 받은 응답을 넣어 주세요")
    if prompt_id == "weekly_rollup" and "items" in value and "headline" not in value:
        raise ResponseFormatError(prompt_id, "누적 요약(cumulative_update) 응답으로 보입니다. 이 단계의 프롬프트를 AI에 보내 받은 응답을 넣어 주세요")
    for key in shape["objects"]:
        if not isinstance(value.get(key), dict):
            raise ResponseFormatError(prompt_id, f'"{key}" 객체가 필요합니다 (받은 최상위 키: {found})')
    for key in shape["lists"]:
        if not isinstance(value.get(key), list):
            raise ResponseFormatError(prompt_id, f'"{key}" 배열이 필요합니다 (받은 최상위 키: {found})')
    for key in shape["optional"]:
        if key in value and value[key] is not None and not isinstance(value[key], list):
            raise ResponseFormatError(prompt_id, f'"{key}"는 배열이어야 합니다')
    for key in (ITEM_LISTS & set(value)) | set(shape["objects"]):
        entries = value[key] if isinstance(value[key], list) else [value[key]]
        for index, item in enumerate(entries):
            where = key if key in shape["objects"] else f"{key}[{index}]"
            if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
                raise ResponseFormatError(prompt_id, f'{where}: {{"text": "...", "source_ids": [...]}} 형식이어야 합니다')
            sources = item.get("source_ids", [])
            if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
                raise ResponseFormatError(prompt_id, f"{where}.source_ids: 문자열 배열이어야 합니다")


def read_payload(text: str, prompt_id: str) -> dict[str, Any]:
    """응답 원문 → 정리된 payload (JSON이 아니면 JSONDecodeError, 형식이 틀리면 ResponseFormatError)."""
    value = normalize_payload(parse_json_value(text, prompt_id), prompt_id)
    check_payload(value, prompt_id)
    return value


# 잠깐 뒤 다시 보내면 되는 오류 (게이트웨이·과부하). 연결 실패·시간 초과도 다시 보낸다.
TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}
RETRY_DELAYS = (3.0, 10.0)  # 다시 보내기 전 대기(초). 길이 = 추가 시도 횟수
LENGTH_HINT = "응답 길이 한도에 걸려 잘렸습니다 — 환경변수 EXAONE_MAX_TOKENS를 늘리거나(사고형 모델은 사고 과정도 한도에 포함) 입력을 나눠 만드세요"


class ExaoneClient:
    def __init__(self, root: Path, mode: str = "mock", transport: Transport | None = None,
                 adapter: Adapter | None = None, timeout: float = 60, mock_dir: Path | None = None):
        if mode not in {"mock", "live"}:
            raise ValueError(f"지원하지 않는 AI 모드: {mode}")
        self.root, self.mode, self.timeout = root, mode, timeout
        self.transport = transport or UrlLibTransport(os.getenv("EXAONE_REQUEST_ID_HEADER", REQUEST_ID_HEADER).strip() or None)
        self.adapter = adapter or ChatCompletionsAdapter()
        self.mock_dir = mock_dir or root / "prompts/mock_responses"
        self.calls: list[str] = []  # 호출 기록 (테스트·보고용, 프롬프트 원문은 남기지 않음)
        self.notes: list[str] = []  # 호출 중 자동 조치 기록 (재요청 등)
        self.call_log: list[dict[str, Any]] = []  # live 호출 계측: 단계·입력 글자 수·걸린 초·보낸 횟수·끝난 이유
        self.retry_delays: tuple[float, ...] = RETRY_DELAYS
        self.sleep = time.sleep  # 테스트에서 바꿔 끼운다
        # 호환 형식(system을 user에 합치고 temperature·max_tokens 없음): None=5xx가 끝까지 나면 한 번 시도, True=처음부터, False=안 씀
        compat = os.getenv("EXAONE_COMPAT_MODE", "auto").strip().lower()
        self.compat: bool | None = True if compat in {"1", "true", "yes", "on"} else False if compat in {"0", "false", "no", "off"} else None
        if self.adapter.__class__ is ChatCompletionsAdapter and os.getenv("EXAONE_MAX_TOKENS", "").strip().isdigit():
            self.adapter.max_tokens = int(os.environ["EXAONE_MAX_TOKENS"]) or None

    @property
    def model_label(self) -> str:
        if self.mode == "mock":
            return "mock"
        return f"{os.getenv('EXAONE_MODEL') or 'EXAONE'} (사내 API, 계약 미검증)"

    def mock_path(self, prompt_id: str, project_id: str, week: str, variant: str | None = None) -> Path:
        suffix = f"__{variant}" if variant else ""
        return self.mock_dir / f"{prompt_id}__{project_id}__{week}{suffix}.json"

    def complete(self, prompt_id: str, project_id: str, week: str, system: str, user: str,
                 variant: str | None = None) -> dict[str, Any]:
        self.calls.append(f"{prompt_id}:{project_id}:{week}:{variant or ''}")
        if self.mode == "mock":
            path = self.mock_path(prompt_id, project_id, week, variant)
            if not path.exists():
                raise MockResponseMissing(f"mock 응답 파일 없음: {path.name}")
            try:
                return read_payload(path.read_text(encoding="utf-8"), prompt_id)
            except json.JSONDecodeError as exc:
                raise ResponseFormatError(prompt_id, f"JSON이 아닙니다 ({path.name})") from exc
        return self._live(prompt_id, system, user)

    def _send(self, url: str, key: str, body: dict[str, Any], stat: dict[str, Any]) -> bytes:
        """한 번 보내기 + 일시 오류(5xx·429·연결·시간 초과)는 대기 후 다시 보낸다."""
        waits = [] if stat.get("no_retry") else list(self.retry_delays)
        while True:
            stat["sends"] += 1
            try:
                try:
                    return self.transport.request(url, key, body, self.timeout)
                finally:  # 사내 담당자 문의용 요청 ID (헤더로 보낸 값)
                    stat["request_id"] = getattr(self.transport, "last_request_id", None)
            except urllib.error.HTTPError as exc:
                if exc.code not in TRANSIENT_CODES or not waits:
                    raise
                reason = f"HTTP {exc.code}"
            except (TimeoutError, socket.timeout):
                if not waits:
                    raise
                reason = f"시간 초과({self.timeout:g}초)"
            except urllib.error.URLError as exc:
                if not waits:
                    raise
                reason = f"연결 실패({type(exc.reason).__name__})"
            wait = waits.pop(0)
            self.notes.append(f"{prompt_label(stat['prompt'])}: {reason} → {wait:g}초 뒤 다시 요청")
            self.sleep(wait)

    def _live(self, prompt_id: str, system: str, user: str) -> dict[str, Any]:
        url, key = os.getenv("EXAONE_API_URL"), os.getenv("EXAONE_API_KEY")
        if not url or not key:
            raise AIError("live 모드는 환경변수 EXAONE_API_URL과 EXAONE_API_KEY가 필요합니다")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        stat: dict[str, Any] = {"prompt": prompt_id, "chars": len(system) + len(user), "sends": 0, "seconds": 0.0, "finish": None}
        self.call_log.append(stat)
        started = time.monotonic()
        try:
            return self._live_loop(prompt_id, url, key, messages, stat)
        finally:
            stat["seconds"] = round(time.monotonic() - started, 1)

    def _body(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """요청 본문. 호환 형식이면 system 내용을 첫 user 메시지 앞에 합치고 temperature·max_tokens를 뺀다."""
        if not self.compat:
            return self.adapter.build_request(messages, os.getenv("EXAONE_MODEL"))
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        merged = [dict(m) for m in messages if m["role"] != "system"]
        if system and merged:
            merged[0]["content"] = f"{system}\n\n{merged[0]['content']}"
        body = self.adapter.build_request(merged, os.getenv("EXAONE_MODEL"))
        body.pop("temperature", None)
        body.pop("max_tokens", None)
        return body

    def _live_loop(self, prompt_id: str, url: str, key: str, messages: list[dict[str, str]], stat: dict[str, Any]) -> dict[str, Any]:
        tries = lambda: (f" (요청 {stat['sends']}회)" if stat["sends"] > 1 else "") + \
            (f" · 요청 ID {stat['request_id']}" if stat.get("request_id") else "")  # noqa: E731 - 사내 담당자 문의용
        attempt = -1
        while attempt < 1:
            attempt += 1
            body = self._body(messages)
            try:
                raw_bytes = self._send(url, key, body, stat)
            except urllib.error.HTTPError as exc:
                if exc.code >= 500 and self.compat is None:
                    # 재요청해도 5xx: 게이트웨이가 이 요청 모양을 처리하지 못할 수 있다 → 호환 형식으로 한 번 더, 되면 계속 사용
                    self.compat = True
                    stat["no_retry"] = True
                    self.notes.append(f"{prompt_label(prompt_id)}: HTTP {exc.code}가 계속되어 호환 형식(system을 user에 합침, temperature 없음)으로 다시 요청")
                    attempt -= 1
                    continue
                hint = f" · 입력 {stat['chars']:,}자 — 입력 길이가 원인일 수 있음" if exc.code >= 500 else ""
                raise AIError(f"EXAONE HTTP 오류: {exc.code}{tries()}{hint}") from None
            except (TimeoutError, socket.timeout):
                raise AIError(f"EXAONE 응답 시간 초과({self.timeout:g}초){tries()}") from None
            except urllib.error.URLError as exc:
                raise AIError(f"EXAONE 연결 실패: {type(exc.reason).__name__}{tries()}") from None
            text = None
            try:
                raw = json.loads(raw_bytes)
                extract = getattr(self.adapter, "extract", None)
                reply = extract(raw) if extract else Reply(self.adapter.extract_text(raw), None, None)
                stat["finish"] = reply.finish_reason
                text = reply.text
                return self._read_reply(reply, prompt_id)
            except LengthExceeded:
                raise AIError(f"{prompt_label(prompt_id)}: {LENGTH_HINT}") from None
            except (json.JSONDecodeError, ResponseFormatError, KeyError, IndexError, TypeError, AttributeError) as exc:
                if attempt:
                    detail = f": {exc}" if isinstance(exc, ResponseFormatError) else ""
                    raise AIError(f"EXAONE 응답을 2회 모두 요구 형식의 JSON으로 받지 못했습니다{detail}") from None
                # 문서 규칙: 파싱 실패 시 1회 재요청
                if isinstance(text, str) and text.strip():
                    messages.append({"role": "assistant", "content": strip_reasoning(text)[:4000]})
                retry = RETRY_MESSAGE if not isinstance(exc, ResponseFormatError) else \
                    f"직전 응답이 요구한 형식이 아닙니다 ({exc}). [출력 JSON 형식]에 맞춰 JSON으로만 다시 출력하세요."
                messages.append({"role": "user", "content": retry})
        raise AssertionError("도달 불가")

    def _read_reply(self, reply: "Reply", prompt_id: str) -> dict[str, Any]:
        """본문 → payload. 본문이 비었거나 형식이 틀리면 사고 과정(reasoning)에서도 찾는다.
        길이 한도로 잘려 읽을 수 없으면 LengthExceeded (같은 요청을 다시 보내도 또 잘리므로 재요청하지 않는다)."""
        try:
            return read_payload(reply.text, prompt_id)
        except (json.JSONDecodeError, ResponseFormatError) as exc:
            if reply.reasoning:
                try:
                    payload = read_payload(reply.reasoning, prompt_id)
                    self.notes.append(f"{prompt_label(prompt_id)}: 본문 대신 사고 과정(reasoning)에서 JSON을 읽음")
                    return payload
                except (json.JSONDecodeError, ResponseFormatError):
                    pass
            if reply.finish_reason == "length":
                raise LengthExceeded() from exc
            raise
