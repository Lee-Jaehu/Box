from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol


class Transport(Protocol):
    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes: ...


class UrlLibTransport:
    def request(self, url: str, key: str, body: dict[str, Any], timeout: float) -> bytes:
        request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()


class ExaoneClient:
    """Mock과 교체 가능한 live 전송 어댑터. live 응답 계약은 아직 미검증이다."""

    def __init__(self, root: Path, mode: str = "mock", transport: Transport | None = None, timeout: float = 30):
        self.root, self.mode, self.transport, self.timeout = root, mode, transport or UrlLibTransport(), timeout

    def complete(self, prompt_id: str, project_id: str, week: str, system: str, user: str) -> dict[str, Any]:
        if self.mode == "mock":
            path = self.root / "prompts/mock_responses" / f"{prompt_id}__{project_id}__{week}.json"
            return json.loads(path.read_text(encoding="utf-8"))
        if self.mode != "live":
            raise ValueError(f"지원하지 않는 AI 모드: {self.mode}")
        url, key = os.getenv("EXAONE_API_URL"), os.getenv("EXAONE_API_KEY")
        if not url or not key:
            raise RuntimeError("live 모드는 EXAONE_API_URL과 EXAONE_API_KEY가 필요합니다")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in range(2):
            body = {"messages": messages, "temperature": 0.1, "response_format": {"type": "json_object"}}
            try:
                raw = json.loads(self.transport.request(url, key, body, self.timeout))
                content = raw.get("content") or raw.get("choices", [{}])[0].get("message", {}).get("content")
                return json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
            except (json.JSONDecodeError, KeyError, TypeError):
                if attempt:
                    raise RuntimeError("EXAONE 응답을 2회 모두 JSON으로 파싱하지 못했습니다")
                messages.append({"role": "user", "content": "직전 응답이 JSON 형식이 아닙니다. 같은 내용을 JSON으로만 다시 출력하세요."})
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
                raise RuntimeError(f"EXAONE 요청 실패: {type(exc).__name__}") from exc
        raise AssertionError
