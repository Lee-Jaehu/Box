"""pptgen: 기준정보 + weekly + cumulative → 회사 주간업무 PPT.

흐름: 템플릿 검사 → JSON 스키마 검증 → milestone_updates 메모리 덧씌우기 → 내용 구성(Rule)
      → 분량 검사·fit_to_budget(AI, 넘칠 때만) → 페이지 나누기(최대 2장) → 렌더 → 재검사 보고서
"""

from __future__ import annotations

from pathlib import Path

from .ai import ExaoneClient
from .codes import CodeTable
from .core import ValidationError, load_json, validate_schema
from .ppt.budget import fit_sections, paginate
from .ppt.compose import build_content
from .ppt.inspect import inspect_pptx
from .ppt.milestones import apply_updates, collapse_milestones, layout_milestones  # noqa: F401  (하위 호환 공개 API)
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


def generate_ppt(root: Path, project_path: Path, weekly_path: Path, cumulative_path: Path, template: Path, output: Path,
                 *, client: ExaoneClient | None = None, mode: str = "mock", report_path: Path | None = None,
                 project_index: int = 1, project_total: int = 1) -> list[str]:
    """PPT를 만들고 경고·검사 결과 목록을 돌려준다. 결과는 report_path(기본: output 옆)에도 남긴다."""
    prs = open_template(template)  # 템플릿 누락·필수 도형 누락은 가장 먼저 보고
    geom = read_geometry(prs.slides[0])

    project, weekly, cumulative = load_json(project_path), load_json(weekly_path), load_json(cumulative_path)
    validate_schema(project, root / "schemas/project.schema.json")
    validate_schema(weekly, root / "schemas/weekly.schema.json")
    validate_schema(cumulative, root / "schemas/cumulative.schema.json")
    pid = project["project_id"]
    if weekly["project_id"] != pid or cumulative["project_id"] != pid:
        raise ValidationError(f"project_id 불일치: 기준정보 {pid}, weekly {weekly['project_id']}, cumulative {cumulative['project_id']}")
    if cumulative["as_of_week"] != weekly["week"]:
        raise ValidationError(f"주차 불일치: weekly {weekly['week']}, cumulative {cumulative['as_of_week']}")

    overlaid, warnings, changed = apply_updates(project, weekly)  # baseline·원본 파일은 바꾸지 않는다
    codes = CodeTable.load(root)
    content = build_content(overlaid, weekly, cumulative, codes, changed,
                            project_index=project_index, project_total=project_total)
    notes = list(warnings) + content.notes
    notes += fit_sections(content, client if client is not None else ExaoneClient(root, mode), root)
    pages, page_notes = paginate(content, geom)
    notes += page_notes
    render(template, content, pages, output)

    problems = inspect_pptx(output, content, pages)
    computed = [c for page in pages for row in page.ms_rows for c in row.computed]
    lines = [f"PPT: {output.name}", f"템플릿: {template.name}", f"슬라이드: {len(pages)}장", "", "[처리 내역]"]
    lines += [f"- {n}" for n in notes] or ["- 없음"]
    lines += ["", "[코드 계산값 (AI 수치 아님)]"] + ([f"- {c}" for c in computed] or ["- 없음"])
    lines += ["", "[PPT 재검사]"] + ([f"- 문제: {p}" for p in problems] or ["- 통과 (색·글꼴·9pt·표 값·상태 배경·슬라이드 수·영역 경계)"])
    report = report_path or output.with_name(f"{output.stem}_ppt_check.txt")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return notes + [f"PPT 검사 문제: {p}" for p in problems]
