"""법인·공정 코드표(config/code_table_site_process.json) 조회와 표시명 변환."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import load_json

SITE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])ES[A-Z][A-Z0-9_]*")


def compact_units(units: list[str]) -> str:
    """["#2-2", "#2-3"] → "#2-2·3" (공통 접두어가 있으면 뒤쪽만 이어 붙인다)."""
    if not units:
        return ""
    prefixes = {u.rsplit("-", 1)[0] for u in units if "-" in u}
    if len(prefixes) == 1 and all("-" in u for u in units):
        prefix = prefixes.pop()
        return prefix + "-" + "·".join(u.rsplit("-", 1)[1] for u in units)
    return "·".join(units)


@dataclass
class CodeTable:
    data: dict[str, Any]

    @classmethod
    def load(cls, root: Path) -> "CodeTable":
        return cls(load_json(root / "config/code_table_site_process.json"))

    def _index(self, key: str, label: str) -> dict[str, str]:
        return {v["code"]: (v.get(label) or v["code"]) for v in self.data.get(key, [])}

    def site_label(self, code: str | None) -> str:
        return self._index("sites", "name").get(code, code) if code else ""

    def line_label(self, code: str | None) -> str:
        return self._index("lines", "label").get(code, code) if code else ""

    def process_label(self, code: str | None) -> str:
        return self._index("processes", "name").get(code, code) if code else ""

    def region_label(self, code: str | None) -> str:
        return self._index("regions", "label").get(code, code) if code else ""

    def unknown_codes(self, part: dict[str, Any]) -> list[str]:
        """코드표에 없는 코드 목록 (표시는 코드 그대로 하고 경고만 남긴다)."""
        checks = (("site", "sites"), ("line", "lines"), ("process", "processes"), ("region", "regions"), ("plant", "plants"))
        missing = []
        for field, key in checks:
            value = part.get(field)
            if value and value not in {v["code"] for v in self.data.get(key, [])}:
                missing.append(f"{field}={value}")
        return missing

    def part_label(self, part: dict[str, Any], *, detail: bool = False) -> str:
        """적용 범위 한 건 → "{법인} {라인}·{공정명}". detail=True면 모델·호기·대수를 다음 줄에 붙인다."""
        if part.get("region"):
            head = self.region_label(part["region"])
        else:
            head = " ".join(filter(None, [self.site_label(part.get("site")), part.get("plant") or "", self.line_label(part.get("line"))]))
        process = self.process_label(part.get("process"))
        label = f"{head}·{process}" if head and process else (head or process)
        if detail:
            extra = " ".join(filter(None, [
                part.get("model") or "",
                compact_units(part.get("units") or []),
                f"{part['units_count']}대" if part.get("units_count") else "",
            ]))
            if extra:
                label += "\n" + extra
        return label

    def scope_label(self, scope: Any) -> str:
        if scope == "common":
            return "공통"
        return ", ".join(self.part_label(part) for part in scope)

    def target_label(self, target: list[dict[str, Any]]) -> str:
        return "\n".join(self.part_label(part, detail=True) for part in target)

    def resolve_site_alias(self, token: str) -> str | None:
        """사이트 표기 → 코드. 'ES' 접두어 규칙은 남은 값이 등록 코드·별칭과 정확히 일치할 때만 적용한다."""
        for site in self.data.get("sites", []):
            if token == site["code"] or token in site.get("aliases", []):
                return site["code"]
        if token.startswith("ES") and len(token) > 2:
            return self.resolve_site_alias(token[2:]) if not token[2:].startswith("ES") else None
        return None

    def unresolved_site_tokens(self, text: str) -> list[str]:
        """문장 속 'ES…' 사이트 표기 중 코드표로 확정할 수 없는 것 (예: ESMI1)."""
        product_codes = {v["code"] for values in self.data.get("product", {}).values() for v in values}
        found = []
        for token in SITE_TOKEN_RE.findall(text):
            if token in product_codes:
                continue
            if self.resolve_site_alias(token) is None and token not in found:
                found.append(token)
        return found


@dataclass
class PeopleTable:
    """config/people.json: 사용자 ID → 이름·직급 (PPT 작성자·담당자 표시용)."""

    data: dict[str, Any]

    @classmethod
    def load(cls, root: Path) -> "PeopleTable":
        path = root / "config/people.json"
        if not path.exists():
            return cls({"people": {}})
        data = load_json(path)
        if not isinstance(data.get("people"), dict):
            raise ValueError("config/people.json: people 객체가 필요합니다")
        return cls(data)

    def _entry(self, user_id: str) -> dict[str, Any] | None:
        entry = self.data["people"].get(user_id)
        return entry if isinstance(entry, dict) and entry.get("name") else None

    def name(self, user_id: str) -> str:
        entry = self._entry(user_id)
        return entry["name"] if entry else user_id

    def name_with_title(self, user_id: str) -> str:
        entry = self._entry(user_id)
        if not entry:
            return user_id
        return " ".join(filter(None, [entry["name"], entry.get("title") or ""]))

    def missing(self, user_ids: list[str]) -> list[str]:
        return [u for u in dict.fromkeys(user_ids) if not self._entry(u)]
