"""PPT에 들어갈 내용 모델 (python-pptx 비의존)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .milestones import MsRow


@dataclass
class Run:
    text: str
    blue: bool = False
    bold: bool = False
    color: str | None = None  # 보고 자료용: 지정하면 이 색(RRGGBB)을 쓴다 (주간 PPT는 blue만 사용)
    highlight: bool = False  # 보고 자료용: 노랑 형광 (결론 핵심 구절)


@dataclass
class Para:
    runs: list[Run]
    kind: str = "text"  # heading / item / blank / text

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


def cell_paras(value: "Run | list[Para]") -> list[Para]:
    """main_table 칸 값 → 문단 목록 (Run의 줄바꿈은 문단으로 나눈다)."""
    if isinstance(value, Run):
        return [Para([Run(line, value.blue, value.bold)]) for line in value.text.split("\n")]
    return value


def cell_text(value: "Run | list[Para]") -> str:
    return "\n".join(p.text for p in cell_paras(value))


@dataclass
class BodyItem:
    text: str
    source_ids: list[str]
    changed: bool = False
    kind: str = "fact"
    blue: bool = False
    overflow: bool = False  # 분량 초과로 (계속) 장에 보낼 항목


@dataclass
class Section:
    key: str  # cumulative / progress / next_plan / issues
    heading: str
    items: list[BodyItem]
    limit: int


@dataclass
class SlideContent:
    """과제 1건의 내용 (페이지 나누기 전)."""

    project_id: str
    week: str
    title: str
    pjt_name: str
    author: str
    updated_at: str
    main: dict[str, Run | list[Para]]  # name, target, week_header, headline, schedule(여러 문단), owner
    body_top: list[Para]
    ms_rows: list[MsRow]
    ms_overflow: list[MsRow]
    sections: list[Section]
    notes: list[str] = field(default_factory=list)


@dataclass
class PageModel:
    continued: bool
    pjt_header: str
    body_top: list[Para]
    ms_rows: list[MsRow]
    body: list[Para]
    body_lines: int = 0
    body_capacity: int = 0
    rule_lines: int = 0
