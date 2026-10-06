"""본문 문서 계약 검증 (프런트 document.ts 와 같은 규칙).

알 수 없는 node/mark는 조용히 삭제하지 않고 위치와 함께 422로 반환한다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from .config import Settings
from .errors import ApiError

DOCUMENT_VERSION = 1
DOCUMENT_FORMAT = "tiptap-json"
ALLOWED_NODES = {
    "doc", "paragraph", "text", "heading", "bulletList", "orderedList", "listItem", "taskList", "taskItem",
    "table", "tableRow", "tableHeader", "tableCell", "image", "gantt", "hardBreak",
}
ALLOWED_MARKS = {"bold", "italic", "underline", "strike", "link"}
LINK_SCHEMES = {"http", "https", "mailto"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def make_document(text: str) -> dict:
    """결과 한 줄 같은 평문으로 문서 envelope 생성."""
    para: dict[str, Any] = {"type": "paragraph"}
    if text.strip():
        para["content"] = [{"type": "text", "text": text.strip()}]
    return {"documentVersion": DOCUMENT_VERSION, "format": DOCUMENT_FORMAT, "doc": {"type": "doc", "content": [para]}}


def _is_iso_date(v: Any) -> bool:
    if not isinstance(v, str) or not _DATE_RE.match(v):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def _issue(path: str, code: str, message: str) -> dict[str, str]:
    return {"field": path, "code": code, "message": message}


def validate_document(document: Any, settings: Settings, field: str = "content") -> tuple[list[dict[str, str]], list[str]]:
    """(issues, imageUseIds) 반환. 이슈가 있으면 호출자가 422를 만든다."""
    issues: list[dict[str, str]] = []
    use_ids: list[str] = []
    if not isinstance(document, dict):
        return [_issue(field, "INVALID_DOCUMENT", "문서 형식이 올바르지 않습니다.")], use_ids
    if document.get("documentVersion") != DOCUMENT_VERSION:
        issues.append(_issue(f"{field}.documentVersion", "UNSUPPORTED_VERSION", "지원하지 않는 문서 버전입니다."))
    if document.get("format") != DOCUMENT_FORMAT:
        issues.append(_issue(f"{field}.format", "UNSUPPORTED_FORMAT", "지원하지 않는 문서 형식입니다."))
    doc = document.get("doc")
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        issues.append(_issue(f"{field}.doc", "INVALID_DOCUMENT", "doc 루트가 필요합니다."))
        return issues, use_ids
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > settings.max_document_bytes:
        issues.append(_issue(field, "DOCUMENT_TOO_LARGE", "문서 크기가 허용치를 넘었습니다."))
        return issues, use_ids

    count = 0

    def walk(node: Any, path: str, depth: int) -> None:
        nonlocal count
        count += 1
        if count > settings.max_document_nodes:
            if count == settings.max_document_nodes + 1:
                issues.append(_issue(path, "TOO_MANY_NODES", "문서 node 수가 허용치를 넘었습니다."))
            return
        if depth > settings.max_document_depth:
            issues.append(_issue(path, "TOO_DEEP", "문서 중첩이 너무 깊습니다."))
            return
        if not isinstance(node, dict) or node.get("type") not in ALLOWED_NODES:
            t = node.get("type") if isinstance(node, dict) else None
            issues.append(_issue(path, "UNKNOWN_NODE", f"알 수 없는 node: {t}"))
            return
        t = node["type"]
        for mark in node.get("marks") or []:
            if not isinstance(mark, dict) or mark.get("type") not in ALLOWED_MARKS:
                issues.append(_issue(path, "UNKNOWN_MARK", f"알 수 없는 mark: {mark.get('type') if isinstance(mark, dict) else mark}"))
            elif mark["type"] == "link":
                href = (mark.get("attrs") or {}).get("href")
                if not isinstance(href, str) or urlparse(href).scheme.lower() not in LINK_SCHEMES:
                    issues.append(_issue(path, "UNSAFE_LINK", "허용되지 않는 링크 주소입니다."))
        attrs = node.get("attrs") or {}
        if t == "image":
            use_id = attrs.get("attachmentUseId")
            if not isinstance(use_id, str) or not use_id:
                issues.append(_issue(path, "IMAGE_WITHOUT_ATTACHMENT", "이미지는 첨부 사용처 ID가 필요합니다."))
            else:
                use_ids.append(use_id)
        elif t == "gantt":
            seen: set[str] = set()
            for i, item in enumerate(attrs.get("items") or []):
                ipath = f"{path}.attrs.items[{i}]"
                if not isinstance(item, dict) or not item.get("itemId"):
                    issues.append(_issue(ipath, "INVALID_GANTT_ITEM", "itemId가 필요합니다."))
                    continue
                if item["itemId"] in seen:
                    issues.append(_issue(ipath, "DUPLICATE_GANTT_ITEM", "itemId가 중복됩니다."))
                seen.add(item["itemId"])
                if not str(item.get("label", "")).strip():
                    issues.append(_issue(ipath, "INVALID_GANTT_ITEM", "작업 이름이 필요합니다."))
                s, e = item.get("startDate"), item.get("endDate")
                if not (_is_iso_date(s) and _is_iso_date(e)):
                    issues.append(_issue(ipath, "INVALID_GANTT_ITEM", "날짜 형식이 올바르지 않습니다."))
                elif e < s:
                    issues.append(_issue(ipath, "INVALID_GANTT_ITEM", "종료일은 시작일보다 빠를 수 없습니다."))
        for i, child in enumerate(node.get("content") or []):
            walk(child, f"{path}.content[{i}]", depth + 1)

    walk(doc, f"{field}.doc", 0)
    return issues, use_ids


def require_valid(document: Any, settings: Settings, field: str) -> list[str]:
    issues, use_ids = validate_document(document, settings, field)
    if issues:
        raise ApiError(422, "INVALID_DOCUMENT", "문서 검증에 실패했습니다.", field_errors=issues)
    return use_ids


def has_content(node: dict) -> bool:
    if node.get("type") == "text":
        return bool(str(node.get("text", "")).strip())
    if node.get("type") in {"image", "gantt", "table"}:
        return True
    return any(has_content(c) for c in node.get("content") or [])


def title_preview(document: dict, limit: int = 60) -> str:
    parts: list[str] = []

    def walk(n: dict) -> None:
        if n.get("type") == "text" and n.get("text"):
            parts.append(n["text"])
        for c in n.get("content") or []:
            walk(c)

    walk(document.get("doc") or {})
    text = " ".join(" ".join(parts).split())
    return text if len(text) <= limit else text[:limit] + "…"
