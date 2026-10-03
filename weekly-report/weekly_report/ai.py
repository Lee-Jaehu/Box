"""EXAONE 클라이언트.

- mock(기본): prompts/mock_responses/{prompt_id}__{project_id}__{week}[__{variant}].json 을 응답으로 사용
- live: EXAONE_API_URL / EXAONE_API_KEY (선택: EXAONE_MODEL) 사용.
  요청·응답 변환은 Adapter로 분리했다. 실제 사내 API 계약은 확인되지 않았으므로
  현재 어댑터(Chat Completions 형식)는 "미검증"이다.
"""

from __future__ import annotations

import json
import os
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
    """OpenAI 호환 Chat Completions 형식 (미검증 가정)."""

    def build_request(self, messages: list[dict[str, str]], model: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"messages": messages, "temperature": 0.1, "response_format": {"type": "json_object"}}
        if model:
            body["model"] = model
        return body

    def extract_text(self, raw: dict[str, Any]) -> str:
        if isinstance(raw.get("content"), str):
            return raw["content"]
        return raw["choices"][0]["message"]["content"]


def parse_json_text(text: str) -> dict[str, Any]:
    """앞뒤 ```json 표시를 제거한 뒤 JSON 객체로 파싱한다."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    value = json.loads(cleaned.strip())
    if not isinstance(value, dict):
        raise json.JSONDecodeError("JSON 객체가 아님", cleaned, 0)
    return value


class ExaoneClient:
    def __init__(self, root: Path, mode: str = "mock", transport: Transport | None = None,
                 adapter: Adapter | None = None, timeout: float = 60, mock_dir: Path | None = None):
        if mode not in {"mock", "live"}:
            raise ValueError(f"지원하지 않는 AI 모드: {mode}")
        self.root, self.mode, self.timeout = root, mode, timeout
        self.transport = transport or UrlLibTransport()
        self.adapter = adapter or ChatCompletionsAdapter()
        self.mock_dir = mock_dir or root / "prompts/mock_responses"
        self.calls: list[str] = []  # 호출 기록 (테스트·보고용, 프롬프트 원문은 남기지 않음)

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
                return parse_json_text(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise AIError(f"mock 응답이 JSON이 아님: {path.name}") from exc
        return self._live(system, user)

    def _live(self, system: str, user: str) -> dict[str, Any]:
        url, key = os.getenv("EXAONE_API_URL"), os.getenv("EXAONE_API_KEY")
        if not url or not key:
            raise AIError("live 모드는 환경변수 EXAONE_API_URL과 EXAONE_API_KEY가 필요합니다")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in range(2):
            body = self.adapter.build_request(messages, os.getenv("EXAONE_MODEL"))
            try:
                raw_bytes = self.transport.request(url, key, body, self.timeout)
            except urllib.error.HTTPError as exc:
                raise AIError(f"EXAONE HTTP 오류: {exc.code}") from None
            except (TimeoutError, socket.timeout) as exc:
                raise AIError(f"EXAONE 응답 시간 초과({self.timeout:g}초)") from None
            except urllib.error.URLError as exc:
                raise AIError(f"EXAONE 연결 실패: {type(exc.reason).__name__}") from None
            text = None
            try:
                text = self.adapter.extract_text(json.loads(raw_bytes))
                return parse_json_text(text)
            except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
                if attempt:
                    raise AIError("EXAONE 응답을 2회 모두 JSON으로 파싱하지 못했습니다") from None
                # 문서 규칙: 파싱 실패 시 1회 재요청
                if isinstance(text, str):
                    messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": RETRY_MESSAGE})
        raise AssertionError("도달 불가")
