"""LG스마트체 글꼴 파일 탐색과 실측값.

- 글꼴 파일은 `fonts/` 또는 weekly-report 폴더의 `LGSM*.TTF`에서 찾는다 (업로드 위치를 옮기지 않는다).
- PPT의 ea 글꼴 이름은 TTF의 이름(nameID 1)과 정확히 같아야 PowerPoint가 해당 글꼴을 쓴다.
- 파일이 없거나 fontTools가 없으면 실측값 대신 보수적인 기본값을 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

EA_REGULAR = "LG스마트체 Regular"
EA_BOLD = "LG스마트체 Bold"
LATIN_FONT = "Arial Narrow"
SAMPLE_HANGUL = "가"


@dataclass(frozen=True)
class FontInfo:
    path: Path
    family: str  # nameID 1 (한국어 이름 우선)
    hangul_em: float  # 한글 한 글자 폭 / em
    line_em: float  # (winAscent + winDescent) / em
    embeddable: bool


@dataclass
class FontSet:
    fonts: dict[str, FontInfo] = field(default_factory=dict)  # family → info
    notes: list[str] = field(default_factory=list)

    @property
    def regular(self) -> FontInfo | None:
        return self.fonts.get(EA_REGULAR)

    @property
    def hangul_em(self) -> float:
        """표 칸 너비 계산용 한글 폭. 글꼴이 없으면 1.0(보수적)."""
        return self.regular.hangul_em if self.regular else 1.0

    def summary(self) -> list[str]:
        if not self.regular:
            return [f"LG스마트체 글꼴 파일 없음 → 한글 폭 1.0em 가정 (ea 이름 '{EA_REGULAR}'은 그대로 지정)"] + self.notes
        lines = [f"{name}: {info.path.name} (한글 폭 {info.hangul_em:.3f}em, 줄 높이 {info.line_em:.3f}em)"
                 for name, info in sorted(self.fonts.items())]
        return lines + self.notes


def _read(path: Path) -> FontInfo | None:
    from fontTools.ttLib import TTFont

    font = TTFont(str(path), lazy=True)
    names = [n for n in font["name"].names if n.nameID == 1]
    korean = [n.toUnicode() for n in names if n.platformID == 3 and n.langID == 0x412]
    family = (korean or [n.toUnicode() for n in names] or [""])[0]
    units = font["head"].unitsPerEm
    glyph = font.getBestCmap().get(ord(SAMPLE_HANGUL))
    if glyph is None:
        return None
    os2 = font["OS/2"]
    return FontInfo(path, family, font["hmtx"][glyph][0] / units, (os2.usWinAscent + os2.usWinDescent) / units,
                    embeddable=not (os2.fsType & 0x0002))


def font_files(root: Path) -> list[Path]:
    candidates = list((root / "fonts").glob("*.[tT][tT][fF]")) if (root / "fonts").is_dir() else []
    candidates += list(root.glob("LGSM*.[tT][tT][fF]"))
    return sorted(dict.fromkeys(candidates))


@lru_cache(maxsize=8)
def load_fonts(root: Path) -> FontSet:
    result = FontSet()
    files = font_files(root)
    if not files:
        return result
    try:
        import fontTools  # noqa: F401
    except ImportError:
        result.notes.append("fontTools 미설치 → 글꼴 실측 생략 (pip install -r requirements.txt)")
        return result
    for path in files:
        try:
            info = _read(path)
        except Exception as exc:  # 손상된 파일 등
            result.notes.append(f"{path.name}: 글꼴을 읽지 못함 ({type(exc).__name__})")
            continue
        if info:
            result.fonts[info.family] = info
    if files and not result.regular:
        result.notes.append(f"글꼴 파일은 있으나 이름이 '{EA_REGULAR}'인 파일이 없음 → ea 이름 불일치 위험")
    return result
