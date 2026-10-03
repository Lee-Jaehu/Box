"""PPT에 들어갈 내용 모델 (python-pptx 비의존)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .milestones import MsRow


@dataclass
class Run:
    text: str
    blue: bool = False
    bold: bool = False


@dataclass
class Para:
    runs: list[Run]
    kind: str = "text"  # heading / item / blank / text

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


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
    main: dict[str, Run]  # name, target, week_header, headline, schedule, owner
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
