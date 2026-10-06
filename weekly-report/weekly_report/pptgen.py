"""pptgen: 기준정보 + weekly + cumulative → 회사 주간업무 PPT.

흐름: 템플릿 검사 → JSON 스키마 검증 → milestone_updates 메모리 덧씌우기 → 내용 구성(Rule)
      → 분량 검사·fit_to_budget(AI, 넘칠 때만) → 페이지 나누기(최대 2장) → 렌더 → 재검사 보고서
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ai import ExaoneClient
from .codes import CodeTable, PeopleTable
from .fonts import FontSet, load_fonts
from .worklog import is_managed, overlay_snapshot
from .core import ValidationError, load_json, validate_schema
from .ppt.budget import LINE_FACTOR_LG, Geometry, MIN_CUMULATIVE, cumulative_room, fit_cumulative_limit, fit_sections, paginate
from .ppt.compose import build_content
from .ppt.model import PageModel, SlideContent
from .ppt.inspect import inspect_pptx
from .ppt.milestones import apply_history, apply_updates, collapse_milestones, layout_milestones, load_prior_weeklies  # noqa: F401
from .ppt.render import REQUIRED_SHAPES, open_template, read_geometry, render

TEMPLATE_NAME = "주간업무PPT_Template_v2.pptx"


def find_template(root: Path, explicit: Path | None = None) -> Path:
    """--template → templates/ → weekly-report 루트 순서로 찾는다. 저장소 루트의 구 양식은 쓰지 않는다."""
    candidates = [explicit] if explicit else [root / "templates" / TEMPLATE_NAME, root / TEMPLATE_NAME]
    for path in candidates:
        if path and path.exists():
            return path
    raise FileNotFoundError(
        f"공식 템플릿 누락: {', '.join(str(p) for p in candidates if p)}; 필수 도형: {', '.join(sorted(REQUIRED_SHAPES))}"
    )


def estimate_cumulative_items(root: Path, project: dict, prior_weeklies: list[dict], weekly: dict,
                              default: int = 7) -> tuple[int, str]:
    """주간 정리 단계에서 누적 요약 최대 항목 수를 PPT 첫 장에 남는 줄 수로 정한다.

    마일스톤 표가 길수록 누적 요약 자리가 줄어든다. 템플릿이 없으면 기본값을 쓴다.
    """
    try:
        prs = open_template(find_template(root))
    except (FileNotFoundError, ValidationError) as exc:
        return default, f"템플릿 없음 → 누적 요약 최대 {default}개 기본값 ({exc.__class__.__name__})"
    geom = read_geometry(prs.slides[0])
    fonts = load_fonts(root.resolve())
    geom.hangul_em = fonts.hangul_em
    if fonts.regular:
        geom.line_factor = LINE_FACTOR_LG
    overlaid, _, changed = apply_history(project, prior_weeklies, weekly)
    stub = {"items": [], "pinned_facts": []}
    content = build_content(overlaid, weekly, stub, CodeTable.load(root), changed, people=PeopleTable.load(root))
    room = cumulative_room(content, geom)
    limit = max(MIN_CUMULATIVE, min(default, room))
    return limit, f"PPT 첫 장 기준 누적 요약 자리 {room}줄 (마일스톤 표 {len(content.ms_rows)}행) → 최대 {limit}개"


def managed_overlay(project: dict, weekly: dict) -> tuple[dict, list[str], set[tuple[str, str]]]:
    """WorkLog 관리 과제: 그 주에 저장한 일정 snapshot 값으로 표를 만들고, 그 주에 바뀐 값만 파란색."""
    overlaid = overlay_snapshot(project, weekly.get("milestone_snapshot"))
    by_source = {m["source_id"]: m["milestone_id"] for m in overlaid["milestones"] if m.get("source_id")}
    snap = weekly.get("milestone_snapshot") or {}
    alias = {v["milestone_id"]: by_source.get(sid) for sid, v in snap.items()}
    changed = {(alias.get(u["milestone_id"]) or u["milestone_id"], u["field"]) for u in weekly.get("milestone_updates", [])}
    rev = (project.get("source") or {}).get("revision")
    notes = [f"WorkLog 일정 기준 (rev {rev}{', 그 주 snapshot 적용' if snap else ''}) — 지난주 대비 바뀐 값 {len(changed)}개 파란색"]
    return overlaid, notes, changed


def weekly_geometry(root: Path, slide) -> tuple[Geometry, FontSet]:
    """주간 장표 배치 기준 + LG스마트체 실측값."""
    geom = read_geometry(slide)
    fonts = load_fonts(root.resolve())
    geom.hangul_em = fonts.hangul_em  # LG스마트체 실측 한글 폭으로 줄 수 계산
    if fonts.regular:
        geom.line_factor = LINE_FACTOR_LG  # LG스마트체 실측 줄 높이
    return geom, fonts


@dataclass
class Prepared:
    """과제 1건의 주간 장표 내용 (렌더 전)."""

    project: dict
    weekly: dict
    cumulative: dict
    content: SlideContent
    pages: list[PageModel]
    notes: list[str]
    current: dict  # 이번 주까지 일정 변화를 덧씌운 기준정보 (메모리 복사본)


def load_inputs(root: Path, project_path: "Path | dict", weekly_path: Path, cumulative_path: Path) -> tuple[dict, dict, dict]:
    """기준정보·weekly·cumulative를 읽고 스키마·ID·주차를 검사한다."""
    # project_path: 기준정보 파일 경로 또는 이미 읽은 과제 dict (WorkLog 과제는 sources.load_project 결과)
    project = project_path if isinstance(project_path, dict) else load_json(project_path)
    weekly, cumulative = load_json(weekly_path), load_json(cumulative_path)
    validate_schema(project, root / "schemas/project.schema.json")
    validate_schema(weekly, root / "schemas/weekly.schema.json")
    validate_schema(cumulative, root / "schemas/cumulative.schema.json")
    pid = project["project_id"]
    if weekly["project_id"] != pid or cumulative["project_id"] != pid:
        raise ValidationError(f"project_id 불일치: 기준정보 {pid}, weekly {weekly['project_id']}, cumulative {cumulative['project_id']}")
    if cumulative["as_of_week"] != weekly["week"]:
        raise ValidationError(f"주차 불일치: weekly {weekly['week']}, cumulative {cumulative['as_of_week']}")
    return project, weekly, cumulative


def prepare_content(root: Path, project_path: "Path | dict", weekly_path: Path, cumulative_path: Path, geom: Geometry,
                    *, client: ExaoneClient | None = None, mode: str = "mock",
                    project_index: int = 1, project_total: int = 1) -> Prepared:
    """내용 구성(Rule) → 분량 검사·fit_to_budget(AI, 넘칠 때만) → 페이지 나누기. 파일은 쓰지 않는다."""
    project, weekly, cumulative = load_inputs(root, project_path, weekly_path, cumulative_path)
    pid = project["project_id"]
    # 이전 주 일정 변화까지 누적해 메모리 복사본에만 적용한다 (baseline·원본 파일은 바꾸지 않음, 파랑은 이번 주만)
    derived_base = weekly_path.resolve().parents[3] if len(weekly_path.resolve().parents) > 3 else root
    prior = load_prior_weeklies(pid, weekly["week"], derived_base, root)
    if is_managed(project):
        overlaid, warnings, changed = managed_overlay(project, weekly)
    else:
        overlaid, warnings, changed = apply_history(project, prior, weekly)
    content = build_content(overlaid, weekly, cumulative, CodeTable.load(root), changed, project_index=project_index,
                            project_total=project_total, people=PeopleTable.load(root).with_project(project))
    notes = list(warnings) + content.notes
    notes += fit_cumulative_limit(content, geom)
    notes += fit_sections(content, client if client is not None else ExaoneClient(root, mode), root)
    pages, page_notes = paginate(content, geom)
    notes += page_notes
    return Prepared(project, weekly, cumulative, content, pages, notes, overlaid)


def check_lines(prepared: Prepared, problems: list[str], fonts: FontSet | None = None) -> list[str]:
    """재검사 보고서의 과제별 부분 (처리 내역·글꼴·계산값·재검사)."""
    computed = [c for page in prepared.pages for row in page.ms_rows for c in row.computed]
    lines = ["[처리 내역]"] + ([f"- {n}" for n in prepared.notes] or ["- 없음"])
    if fonts is not None:
        lines += ["", "[글꼴]"] + [f"- {f}" for f in fonts.summary()]
    lines += ["", "[코드 계산값 (AI 수치 아님)]"] + ([f"- {c}" for c in computed] or ["- 없음"])
    lines += ["", "[PPT 재검사]"] + ([f"- 문제: {p}" for p in problems] or ["- 통과 (색·글꼴·9pt·표 값·상태 배경·슬라이드 수·영역 경계)"])
    return lines


def generate_ppt(root: Path, project_path: "Path | dict", weekly_path: Path, cumulative_path: Path, template: Path, output: Path,
                 *, client: ExaoneClient | None = None, mode: str = "mock", report_path: Path | None = None,
                 project_index: int = 1, project_total: int = 1) -> list[str]:
    """PPT를 만들고 경고·검사 결과 목록을 돌려준다. 결과는 report_path(기본: output 옆)에도 남긴다."""
    prs = open_template(template)  # 템플릿 누락·필수 도형 누락은 가장 먼저 보고
    geom, fonts = weekly_geometry(root, prs.slides[0])
    prepared = prepare_content(root, project_path, weekly_path, cumulative_path, geom, client=client, mode=mode,
                               project_index=project_index, project_total=project_total)
    prepared.notes += render(template, prepared.content, prepared.pages, output, geom)

    problems = inspect_pptx(output, prepared.content, prepared.pages)
    lines = [f"PPT: {output.name}", f"템플릿: {template.name}", f"슬라이드: {len(prepared.pages)}장", ""]
    lines += check_lines(prepared, problems, fonts)
    report = report_path or output.with_name(f"{output.stem}_ppt_check.txt")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prepared.notes + [f"PPT 검사 문제: {p}" for p in problems]
