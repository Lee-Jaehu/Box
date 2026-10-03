from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

# 하위 호환: 분량 계산은 textmetrics 모듈로 이동했다.
from .textmetrics import weighted_length, wrapped_lines  # noqa: F401

KST = timezone(timedelta(hours=9))
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


class ValidationError(ValueError):
    """입력 또는 출력 계약 위반."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def atomic_json(path: Path, value: dict[str, Any], *, updated_by: str = "pipeline") -> None:
    """meta를 갱신하고 같은 디렉터리에서 원자적으로 JSON을 교체한다."""
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    old = load_json(path) if path.exists() else None
    meta = value.setdefault("meta", {})
    meta["revision"] = (old.get("meta", {}).get("revision", 0) + 1) if old else max(meta.get("revision", 1), 1)
    # 기존 파일이 있으면 최초 생성 시각을 보존한다.
    meta["created_at"] = old.get("meta", {}).get("created_at", now) if old else meta.get("created_at", now)
    meta["updated_at"] = now
    meta["updated_by"] = updated_by
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_schema(value: Any, schema_path: Path) -> None:
    errors = sorted(Draft202012Validator(load_json(schema_path)).iter_errors(value), key=lambda e: list(e.absolute_path))
    if errors:
        details = "; ".join(f"{'.'.join(map(str, e.absolute_path)) or '$'}: {e.message}" for e in errors)
        raise ValidationError(details)


def week_range(week: str) -> tuple[date, date]:
    match = WEEK_RE.fullmatch(week)
    if not match:
        raise ValidationError(f"잘못된 ISO 주차: {week}")
    try:
        monday = date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError as exc:
        raise ValidationError(f"잘못된 ISO 주차: {week}") from exc
    return monday, monday + timedelta(days=6)


def previous_week(week: str) -> str:
    monday, _ = week_range(week)
    prev = monday - timedelta(days=7)
    iso = prev.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"




def render_prompt(root: Path, prompt_id: str, variables: dict[str, Any]) -> tuple[str, str]:
    common = (root / "prompts/common_rules.txt").read_text(encoding="utf-8")
    rendered = []
    for suffix in ("system", "user"):
        text = (root / f"prompts/{prompt_id}.{suffix}.txt").read_text(encoding="utf-8")
        values = {"common_rules": common, **{k: str(v) for k, v in variables.items()}}
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        missing = re.findall(r"{{([^}]+)}}", text)
        if missing:
            raise ValidationError(f"프롬프트 변수 누락: {', '.join(sorted(set(missing)))}")
        rendered.append(text)
    return rendered[0], rendered[1]


def item(text: str, sources: list[str], kind: str = "fact", changed: bool = False) -> dict[str, Any]:
    return {"text": text, "source_ids": sources, "kind": kind, "changed": changed}
