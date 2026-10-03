"""PPT 분량 계산용 가중 길이와 줄 나눔.

한글(및 한자) 1, 영문·숫자·기호 0.55로 계산한다 (CLAUDE.md PPT 규칙).
실제 PowerPoint 줄바꿈보다 보수적으로(줄 수가 같거나 많게) 계산하는 것이 목적이다.
"""

from __future__ import annotations

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
