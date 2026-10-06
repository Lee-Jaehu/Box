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
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

RETRY_MESSAGE = "직전 응답이 JSON 형식이 아닙니다. 같은 내용을 JSON으로만 다시 출력하세요."


class AIError(RuntimeError):
    """AI 호출 실패 (키·원문은 메시지에 넣지 않는다)."""


class MockResponseMissing(AIError):
    """mock 응답 파일 없음."""


class Transport(Protocol):
    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes: ...


class UrlLibTransport:
    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes:
        request = urllib.request.Request(
            url, json.dumps(body, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()


class Adapter(Protocol):
    """사내 API 계약이 정해지면 이 인터페이스만 새로 구현한다."""

    def build_request(self, messages: list[dict[str, str]], model: str | None) -> dict[str, Any]: ...

    def extract_text(self, raw: dict[str, Any]) -> str: ...


class ChatCompletionsAdapter:
    """OpenAI 호환 Chat Completions 형식.

    [Worklog 통합] 사내 EXAONE(k-exaone_v2) 게이트웨이는 response_format={"type":"json_object"}에 500
    ("InternalServerError,Connection error.")을 돌려준다(2026-10-06 사용자 PC 확인). 그래서 기본은 붙이지 않는다(json_mode=False).
    프롬프트가 JSON만 요구하고, read_payload가 응답 속 설명 문장·```json 표시를 걸러 JSON만 읽는다.
    """

    def __init__(self, json_mode: bool = False):
        self.json_mode = json_mode

    def build_request(self, messages: list[dict[str, str]], model: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"messages": messages, "temperature": 0.1}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if model:
            body["model"] = model
        return body

    def extract_text(self, raw: dict[str, Any]) -> str:
        if isinstance(raw.get("content"), str):
            return raw["content"]
        return raw["choices"][0]["message"]["content"]


# 프롬프트별 응답 형식: 필수 배열 키, 반드시 객체여야 하는 키, 선택 배열 키
RESPONSE_SHAPES: dict[str, dict[str, tuple[str, ...]]] = {
    "weekly_rollup": {"objects": ("headline",), "lists": (), "optional": ("progress", "next_plan", "issues", "milestone_updates")},
    # [Worklog 통합] 임의 기간 정리: 주간 정리와 같은 응답 형식
    "period_rollup": {"objects": ("headline",), "lists": (), "optional": ("progress", "next_plan", "issues", "milestone_updates")},
    "cumulative_update": {"objects": (), "lists": ("items",), "optional": ("pinned_facts", "new_pinned_facts")},
    "fit_to_budget": {"objects": (), "lists": ("items",), "optional": ("dropped",)},
    # 팀장 요약 페이지 (원본 2026-10-06): items[].category/details는 summary.build_items가 확인
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


class ResponseFormatError(AIError):
    """AI 응답이 JSON이지만 프롬프트가 요구한 형식이 아님."""

    def __init__(self, prompt_id: str, message: str):
        super().__init__(f"{prompt_id} 응답 형식 오류: {message}")
        self.prompt_id = prompt_id


def _json_candidates(text: str) -> list[str]:
    """응답 원문에서 JSON 후보 구간: 전체 → ```json 블록 → 첫 {/[ 부터."""
    cleaned = text.strip().lstrip("\ufeff")
    candidates = [cleaned]
    candidates += [m.group(1) for m in re.finditer(r"```[A-Za-z]*\s*\n?(.*?)```", cleaned, re.S)]
    if cleaned.startswith("```"):  # 닫는 ``` 없이 잘린 경우
        candidates.append(cleaned.split("\n", 1)[1] if "\n" in cleaned else "")
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0]
    if starts:
        candidates.append(cleaned[min(starts):])
    return candidates


def parse_json_value(text: str) -> Any:
    """설명 문장·```json 표시가 섞여 있어도 첫 JSON 객체(또는 배열)를 꺼낸다."""
    decoder = json.JSONDecoder()
    error: json.JSONDecodeError | None = None
    for candidate in _json_candidates(text):
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            error = error or exc
        if candidate[:1] in "{[":
            try:  # JSON 뒤에 설명 문장이 붙은 경우
                return decoder.raw_decode(candidate)[0]
            except json.JSONDecodeError:
                pass
    raise error or json.JSONDecodeError("JSON 없음", text, 0)


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
    rollup = prompt_id in ("weekly_rollup", "period_rollup")
    if not rollup and "headline" in value and "items" not in value:
        raise ResponseFormatError(prompt_id, "주간 정리(weekly_rollup) 응답으로 보입니다. 이 단계의 프롬프트를 AI에 보내 받은 응답을 넣어 주세요")
    if rollup and "items" in value and "headline" not in value:
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
    value = normalize_payload(parse_json_value(text), prompt_id)
    check_payload(value, prompt_id)
    return value


JSON_MODE_REJECT_CODES = {400, 415, 422, 500, 501}


def _error_detail(exc: urllib.error.HTTPError, limit: int = 300) -> str:
    """[Worklog 통합] 서버가 돌려준 오류 본문 앞부분 (원인 파악용, 요청·키는 담지 않음)."""
    try:
        text = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - 본문을 못 읽어도 상태 번호는 알린다
        return ""
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _url_hint(url: str) -> str:
    """오류 메시지용 주소 (쿼리 문자열은 키가 들어 있을 수 있어 뺀다)."""
    return url.split("?", 1)[0]


class ExaoneClient:
    def __init__(self, root: Path, mode: str = "mock", transport: Transport | None = None,
                 adapter: Adapter | None = None, timeout: float = 60, mock_dir: Path | None = None,
                 api_url: str | None = None, api_key: str | None = None, model: str | None = None):
        if mode not in {"mock", "live"}:
            raise ValueError(f"지원하지 않는 AI 모드: {mode}")
        self.root, self.mode, self.timeout = root, mode, timeout
        # [Worklog 통합] 서버 설정값을 직접 받는다. 없으면 기존처럼 환경변수 EXAONE_* 를 쓴다.
        self.api_url = api_url or os.getenv("EXAONE_API_URL")
        self.api_key = api_key or os.getenv("EXAONE_API_KEY")
        self.model = model or os.getenv("EXAONE_MODEL")
        self.transport = transport or UrlLibTransport()
        self.adapter = adapter or ChatCompletionsAdapter()
        self.mock_dir = mock_dir or root / "prompts/mock_responses"
        self.calls: list[str] = []  # 호출 기록 (테스트·보고용, 프롬프트 원문은 남기지 않음)
        self.notes: list[str] = []  # 호출 중 자동 조치 기록 (예: JSON 강제 옵션 끔)

    @property
    def model_label(self) -> str:
        if self.mode == "mock":
            return "mock"
        return f"{self.model or 'EXAONE'} (사내 API, 계약 미검증)"

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

    def _live(self, prompt_id: str, system: str, user: str) -> dict[str, Any]:
        url, key = self.api_url, self.api_key
        if not url or not key:
            raise AIError("live 모드는 API 주소와 키가 필요합니다 (서버 설정 ai_api_url / ai_api_key 또는 환경변수 EXAONE_API_URL / EXAONE_API_KEY)")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        json_retry = False
        attempt = -1
        while attempt < 1:
            attempt += 1
            body = self.adapter.build_request(messages, self.model)
            try:
                raw_bytes = self.transport.request(url, key, body, self.timeout)
            except urllib.error.HTTPError as exc:
                detail = _error_detail(exc)
                if getattr(self.adapter, "json_mode", False) and exc.code in JSON_MODE_REJECT_CODES and not json_retry:
                    # [Worklog 통합] JSON 강제 옵션을 거절하는 서버: 옵션을 빼고 한 번 더 보낸다
                    self.adapter.json_mode = False
                    json_retry = True
                    self.notes.append(f"AI 서버가 JSON 강제 옵션을 거절(HTTP {exc.code}) → 옵션 없이 다시 요청")
                    attempt -= 1  # 형식 재요청 기회는 그대로 남긴다
                    continue
                raise AIError(f"EXAONE HTTP 오류: {exc.code}{f' ({detail})' if detail else ''} — 요청 주소 {_url_hint(url)}") from None
            except (TimeoutError, socket.timeout) as exc:
                raise AIError(f"EXAONE 응답 시간 초과({self.timeout:g}초)") from None
            except urllib.error.URLError as exc:
                raise AIError(f"EXAONE 연결 실패: {type(exc.reason).__name__}") from None
            text = None
            try:
                text = self.adapter.extract_text(json.loads(raw_bytes))
                return read_payload(text, prompt_id)
            except (json.JSONDecodeError, ResponseFormatError, KeyError, IndexError, TypeError, AttributeError) as exc:
                if attempt:
                    detail = f": {exc}" if isinstance(exc, ResponseFormatError) else ""
                    raise AIError(f"EXAONE 응답을 2회 모두 요구 형식의 JSON으로 받지 못했습니다{detail}") from None
                # 문서 규칙: 파싱 실패 시 1회 재요청
                if isinstance(text, str):
                    messages.append({"role": "assistant", "content": text})
                retry = RETRY_MESSAGE if not isinstance(exc, ResponseFormatError) else \
                    f"직전 응답이 요구한 형식이 아닙니다 ({exc}). [출력 JSON 형식]에 맞춰 JSON으로만 다시 출력하세요."
                messages.append({"role": "user", "content": retry})
        raise AssertionError("도달 불가")
