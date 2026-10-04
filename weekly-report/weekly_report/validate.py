"""AI 출력 의미 검증.

구조 검증(JSON Schema)과 분리된 단계다. 구조가 맞는 출력은 저장하고, 여기서 찾은 문제는
항목 경로·사유·근거 구분(출처 태그)과 함께 validation 보고서에 남긴다.

수치 출처 태그
- 원문: 이번 주 Daily 원문·표 값에서 확인
- 기준정보: data/master 과제 기준정보에서 확인
- 이전요약: 지난주 누적 요약·주간 정리본에만 있음 (원문까지는 확인하지 못함)
- 계산값: 코드가 만든 값 (주차, 날짜 범위 등)
- 미확인: 어디에서도 찾지 못함 → 환각 의심 오류
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .codes import CodeTable

ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
MD_DATE_RE = re.compile(r"(?<![\d./])(\d{1,2})/(\d{1,2})(?![\d/])")
RECORD_ID_RE = re.compile(r"(?<![A-Za-z0-9])(?:D|CP|R)-\d{6}-[A-Za-z0-9]+(?:-\d+)?|(?<![A-Za-z0-9])P-[A-Z]+-\d{3}|(?<![A-Za-z0-9])M\d+(?:-\d+)?(?![A-Za-z0-9])")
UNIT_RE = re.compile(r"#\d+(?:-\d+)?(?:[·,]\d+)*")
CODE_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_]+\d[A-Za-z0-9_]*")
NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?%?")
STATUS_VALUES = {"예정", "진행", "지연", "완료", "보류", "취소"}
UPDATE_FIELD_TYPES = {"plan": "date", "actual": "date", "status": "status", "plan_text": "string", "note": "string"}

LEVEL_ORDER = {"오류": 0, "주의": 1, "정보": 2}


@dataclass
class Issue:
    path: str
    level: str  # 오류 / 주의 / 정보
    message: str

    def format(self) -> str:
        return f"[{self.level}] {self.path}: {self.message}"


@dataclass
class Tokens:
    dates: list[tuple[int, int]] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)


def extract_tokens(text: str) -> Tokens:
    """문장을 날짜·근거ID·호기·코드·수치로 나눈다 (앞에서 잡힌 부분은 뒤 단계에서 제외)."""
    found = Tokens()
    rest = text
    for m in ISO_DATE_RE.finditer(rest):
        found.dates.append((int(m[2]), int(m[3])))
    rest = ISO_DATE_RE.sub(" ", rest)
    for m in MD_DATE_RE.finditer(rest):
        found.dates.append((int(m[1]), int(m[2])))
    rest = MD_DATE_RE.sub(" ", rest)
    found.ids = RECORD_ID_RE.findall(rest)
    rest = RECORD_ID_RE.sub(" ", rest)
    found.units = UNIT_RE.findall(rest)
    rest = UNIT_RE.sub(" ", rest)
    found.codes = CODE_RE.findall(rest)
    rest = CODE_RE.sub(" ", rest)
    found.numbers = NUMBER_RE.findall(rest)
    return found


def _decimal(token: str) -> Decimal | None:
    try:
        return Decimal(token.rstrip("%"))
    except InvalidOperation:
        return None


# 기준정보에서 근거로 쓰지 않는 구조용 필드 (순번·버전 등은 보고 내용의 수치가 아니다)
STRUCTURAL_KEYS = {"meta", "order", "template_version", "schema_version", "revision"}


def _flatten(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k not in STRUCTURAL_KEYS:
                yield from _flatten(v)
    elif isinstance(value, list):
        for v in value:
            yield from _flatten(v)
    elif value is not None and not isinstance(value, bool):
        yield str(value)


class Corpus:
    """출처 하나(원문/기준정보/이전요약/계산값)의 토큰 모음."""

    def __init__(self, name: str, texts: Iterable[str]):
        self.name = name
        self.texts = [t for t in texts if t]
        self.joined = "\n".join(self.texts)
        self.numbers: set[str] = set()
        self.dates: set[tuple[int, int]] = set()
        for text in self.texts:
            tokens = extract_tokens(text)
            self.numbers.update(n.rstrip("%") for n in tokens.numbers)
            self.dates.update(tokens.dates)
            # 코드 안의 숫자(S4의 4, E77의 77)는 수치 근거로 쓰지 않는다
        self.decimals = {d for d in (_decimal(n) for n in self.numbers) if d is not None}

    def has_exact(self, number: str) -> bool:
        return number.rstrip("%") in self.numbers

    def equivalents(self, number: str) -> list[str]:
        value = _decimal(number)
        return sorted(n for n in self.numbers if _decimal(n) == value) if value is not None else []

    def has_text(self, token: str) -> bool:
        return token in self.joined


@dataclass
class Evidence:
    raw: Corpus
    master: Corpus
    prev: Corpus
    computed: Corpus
    allowed_ids: set[str]
    codes: CodeTable | None = None
    prev_level: str = "주의"  # 이번 주 문장이 이전 요약에만 있는 수치를 쓰면 주의, 누적 요약이면 정보

    @property
    def ordered(self) -> list[tuple[Corpus, str]]:
        return [(self.raw, "원문"), (self.master, "기준정보"), (self.computed, "계산값"), (self.prev, "이전요약")]


DAILY_ID_DATE_RE = re.compile(r"^(?:D|CP|R)-\d{2}(\d{2})(\d{2})-")


def id_dates(ids: Iterable[str]) -> list[str]:
    """기록 ID에 담긴 작성일 (D-260922-ljh-01 → "9/22"). 문장 끝 진행 날짜의 근거로 쓴다."""
    found = []
    for value in ids:
        match = DAILY_ID_DATE_RE.match(value)
        if match:
            found.append(f"{int(match[1])}/{int(match[2])}")
    return sorted(set(found))


def build_evidence(*, dailies: list[dict[str, Any]], project: dict[str, Any], prev_texts: Iterable[str] = (),
                   computed: Iterable[str] = (), allowed_ids: set[str], codes: CodeTable | None = None,
                   prev_level: str = "주의") -> Evidence:
    raw_texts: list[str] = []
    for daily in dailies:
        raw_texts.append(daily.get("date", ""))  # 메모 작성일: 문장 끝 진행 날짜 "(MM/DD)"의 근거
        raw_texts.append(daily.get("raw_text", ""))
        for table in daily.get("tables", []):
            raw_texts.extend(str(c) for c in table.get("columns", []))
            raw_texts.extend(str(v) for row in table.get("rows", []) for v in row if v is not None)
    master_texts = list(_flatten(project))
    return Evidence(Corpus("원문", raw_texts), Corpus("기준정보", master_texts), Corpus("이전요약", prev_texts),
                    Corpus("계산값", computed), allowed_ids, codes, prev_level)


def check_item(path: str, value: dict[str, Any], evidence: Evidence, *, require_sources: bool = True) -> list[Issue]:
    issues: list[Issue] = []
    text = value.get("text", "")
    sources = value.get("source_ids", [])
    for source in sources:
        if source not in evidence.allowed_ids:
            issues.append(Issue(f"{path}.source_ids", "오류", f"존재하지 않는 근거 {source} (입력으로 준 ID가 아님)"))
    if require_sources and not sources:
        issues.append(Issue(f"{path}.source_ids", "주의", "근거 ID 없음"))
    tokens = extract_tokens(text)
    for number in tokens.numbers:
        issues.extend(_check_number(path, number, evidence))
    for month, day in tokens.dates:
        issues.extend(_check_date(path, month, day, evidence))
    for code in tokens.codes:
        if not any(corpus.has_text(code) for corpus, _ in evidence.ordered):
            issues.append(Issue(f"{path}.text", "오류", f"입력에서 확인되지 않는 표기 {code}"))
    for unit in tokens.units:
        head = re.split(r"[·,]", unit)[0]
        if not any(corpus.has_text(head) for corpus, _ in evidence.ordered):
            issues.append(Issue(f"{path}.text", "오류", f"입력에서 확인되지 않는 호기 {unit}"))
    if evidence.codes is not None:
        for token in evidence.codes.unresolved_site_tokens(text):
            issues.append(Issue(f"{path}.text", "주의", f"미확정 사이트 코드 {token} (코드표로 확정할 수 없어 정상 코드로 처리하지 않음)"))
    return issues


def _check_number(path: str, number: str, evidence: Evidence) -> list[Issue]:
    for corpus, tag in evidence.ordered:
        if corpus.has_exact(number):
            if tag == "이전요약":
                return [Issue(f"{path}.text", evidence.prev_level, f"수치 {number}: 이전 요약에서 승계(이번 주 원문에서는 확인하지 않음)")]
            others = [n for n in corpus.equivalents(number) if n != number.rstrip("%")]
            if others:
                return [Issue(f"{path}.text", "정보", f"수치 {number}: {tag}에 그대로 있음. 같은 {tag}의 {' / '.join(others)}과는 숫자는 같고 표시 정밀도만 다름")]
            return []
    for corpus, tag in evidence.ordered:
        same = corpus.equivalents(number)
        if same:
            return [Issue(f"{path}.text", "주의", f"수치 {number}: {tag} 값 {' / '.join(same)}과 숫자는 같으나 표시 정밀도가 다름")]
    return [Issue(f"{path}.text", "오류", f"입력에서 확인되지 않는 수치 {number}")]


def _check_date(path: str, month: int, day: int, evidence: Evidence) -> list[Issue]:
    label = f"{month}/{day}"
    try:
        date(2000, month, day)
    except ValueError:
        return [Issue(f"{path}.text", "오류", f"존재하지 않는 날짜 {label}")]
    for corpus, tag in evidence.ordered:
        if (month, day) in corpus.dates:
            if tag == "이전요약":
                return [Issue(f"{path}.text", evidence.prev_level, f"날짜 {label}: 이전 요약에서 승계(이번 주 원문에서는 확인하지 않음)")]
            return []
    return [Issue(f"{path}.text", "오류", f"입력에서 확인되지 않는 날짜 {label}")]


def milestone_update_problem(update: dict[str, Any], milestone_ids: set[str]) -> str | None:
    """milestone_updates 한 건의 적용 불가 사유 (없으면 None)."""
    mid, fld, value = update.get("milestone_id"), update.get("field"), update.get("to")
    if mid is None:
        return "milestone_id가 null (해당 단계 없음)"
    if mid not in milestone_ids:
        return f"존재하지 않는 milestone_id {mid}"
    kind = UPDATE_FIELD_TYPES.get(fld)
    if kind is None:
        return f"지원하지 않는 field {fld}"
    if not isinstance(value, str) or not value.strip():
        return f"{fld} 값은 비어 있지 않은 문자열이어야 함 (받은 값: {value!r})"
    if kind == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return f"{fld} 값은 YYYY-MM-DD 날짜여야 함 (받은 값: {value})"
        try:
            date.fromisoformat(value)
        except ValueError:
            return f"{fld} 값이 존재하지 않는 날짜 (받은 값: {value})"
    if kind == "status" and value not in STATUS_VALUES:
        return f"status 값은 {', '.join(sorted(STATUS_VALUES))} 중 하나여야 함 (받은 값: {value})"
    return None


def check_milestone_updates(updates: list[dict[str, Any]], project: dict[str, Any], evidence: Evidence) -> list[Issue]:
    issues: list[Issue] = []
    ids = {m["milestone_id"] for m in project["milestones"]}
    for index, update in enumerate(updates):
        path = f"milestone_updates[{index}]"
        problem = milestone_update_problem(update, ids)
        if problem:
            issues.append(Issue(path, "오류", f"{problem} → PPT에 적용하지 않음"))
        for source in update.get("source_ids", []):
            if source not in evidence.allowed_ids:
                issues.append(Issue(f"{path}.source_ids", "오류", f"존재하지 않는 근거 {source}"))
        if not problem and update.get("field") in {"plan", "actual"}:
            iso = update["to"]
            month, day = int(iso[5:7]), int(iso[8:10])
            for corpus, tag in evidence.ordered[:2]:
                if (month, day) in corpus.dates:
                    break
            else:
                issues.append(Issue(f"{path}.to", "오류", f"날짜 {month}/{day}가 이번 주 원문·기준정보에 없음"))
    return issues


def sort_issues(issues: list[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda i: (LEVEL_ORDER.get(i.level, 9), i.path))
