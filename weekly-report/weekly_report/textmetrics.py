"""PPT 분량 계산용 가중 길이와 줄 나눔.

한글(및 한자) 1, 영문·숫자·기호 0.55로 계산한다 (CLAUDE.md PPT 규칙).
실제 PowerPoint 줄바꿈보다 보수적으로(줄 수가 같거나 많게) 계산하는 것이 목적이다.
"""

from __future__ import annotations

import re

# 본문·요약 문장 규칙 (2026-10-04 결정): 한 항목 = PPT 한 줄, 40~60자(끝의 날짜 포함), 경어체 종결,
# 진행 현황·이슈·누적 요약은 끝에 진행 날짜 "(MM/DD)" 또는 "(MM/DD~MM/DD)"
SENTENCE_MIN = 40.0
SENTENCE_MAX = 60.0
_DATE_NOTE_RE = re.compile(r"^\(~?\d{1,2}/\d{1,2}(?:~(?:\d{1,2}/\d{1,2})?)?\)$")  # (10/08) (~10/16) (09/28~09/30) (09/04~)
_TRAILING_NOTE_RE = re.compile(r"(\s*\.?\s*\([^()]*\))+\s*$")  # 끝의 "(판단)", "(지원 요청)" 같은 표시

WIDE_RANGES = (
    ("가", "힣"),  # 한글 음절
    ("ᄀ", "ᇿ"),  # 한글 자모
    ("㄰", "㆏"),  # 한글 호환 자모
    ("一", "鿿"),  # 한자
)


def char_weight(ch: str) -> float:
    return 1.0 if any(lo <= ch <= hi for lo, hi in WIDE_RANGES) else 0.55


def weighted_length(text: str) -> float:
    return sum(char_weight(ch) for ch in text)


def wrap_text(text: str, width: float = 50.0) -> list[str]:
    """단어(공백) 단위 탐욕 줄 나눔. 한 단어가 width보다 길면 글자 단위로 자른다."""
    if width <= 0:
        raise ValueError("width는 0보다 커야 합니다")
    lines: list[str] = []
    for raw_line in text.split("\n"):
        current, used = "", 0.0
        for word in raw_line.split(" "):
            token = word if not current else " " + word
            token_w = weighted_length(token)
            if used + token_w <= width + 1e-9:
                current, used = current + token, used + token_w
                continue
            if current:
                lines.append(current)
            current, used = "", 0.0
            for ch in word:
                w = char_weight(ch)
                if used + w > width + 1e-9:
                    lines.append(current)
                    current, used = "", 0.0
                current, used = current + ch, used + w
        lines.append(current)
    return lines or [""]


def line_count(text: str, width: float = 50.0) -> int:
    return len(wrap_text(text, width))


# 하위 호환: 기존 core.wrapped_lines 사용처
def wrapped_lines(text: str, width: float = 50.0) -> int:
    return line_count(text, width)


def is_polite(text: str) -> bool:
    """경어체("~습니다/~니다")로 끝나는지. 끝의 괄호 표시와 마침표는 무시한다."""
    body = _TRAILING_NOTE_RE.sub("", text.strip().rstrip(" .")).rstrip(" .")
    return body.endswith("니다")


def has_date_note(text: str) -> bool:
    """문장 끝 괄호 표시 중에 진행 날짜 "(MM/DD)"가 있는지."""
    match = _TRAILING_NOTE_RE.search(text.strip())
    notes = re.findall(r"\([^()]*\)", match.group(0)) if match else []
    return any(_DATE_NOTE_RE.match(note.replace(" ", "")) for note in notes)


def sentence_problems(text: str, *, need_date: bool = False) -> list[str]:
    """문장 규칙 위반 설명 (없으면 빈 목록)."""
    problems = []
    length = weighted_length(text)
    if length < SENTENCE_MIN:
        problems.append(f"{length:.1f}자 < 최소 {SENTENCE_MIN:g}자 (함축적이라 이해하기 어려울 수 있음)")
    elif length > SENTENCE_MAX:
        problems.append(f"{length:.1f}자 > 최대 {SENTENCE_MAX:g}자 (PPT 한 줄 초과)")
    if not is_polite(text):
        problems.append('경어체 종결("~했습니다/~입니다") 아님')
    if need_date and not has_date_note(text):
        problems.append('문장 끝 진행 날짜 "(MM/DD)" 없음')
    return problems
