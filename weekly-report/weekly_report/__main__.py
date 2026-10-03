"""주간업무 자동화 시연 CLI.

python -m weekly_report weekly   P-ASM-001 2026-W39 [--mode mock|live] [--out-root DIR]
python -m weekly_report pptgen   P-ASM-001 2026-W39 [--mode mock|live] [--out-root DIR] [--template PATH] [--output PATH]
python -m weekly_report pipeline P-ASM-001 2026-W39 [--mode mock|live] [--out-root DIR] [--template PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ai import AIError
from .core import ValidationError
from .ppt.budget import BudgetError
from .pptgen import find_template, generate_ppt
from .weekly import run_weekly


def _derived_input(kind: str, project_id: str, week: str, out_root: Path, root: Path) -> Path:
    for base in dict.fromkeys([out_root, root]):
        path = base / f"data/derived/{kind}/{project_id}/{week}.json"
        if path.exists():
            return path
    raise FileNotFoundError(f"{kind} 입력 없음: data/derived/{kind}/{project_id}/{week}.json (먼저 weekly를 실행하세요)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m weekly_report", description="주간업무 자동화 시연 CLI")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="weekly-report 폴더 (기본: 패키지 위치)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("weekly", "Daily → weekly/cumulative JSON"), ("pptgen", "기준정보+weekly+cumulative → PPT"),
                            ("pipeline", "weekly 후 pptgen")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("project_id")
        cmd.add_argument("week", help="ISO 주차, 예: 2026-W39")
        cmd.add_argument("--mode", choices=("mock", "live"), default="mock")
        cmd.add_argument("--out-root", type=Path, help="data/derived·output을 쓸 위치 (기본: --root)")
        if name != "weekly":
            cmd.add_argument("--template", type=Path, help="기본: templates/ → weekly-report/ 의 주간업무PPT_Template_v2.pptx")
        if name == "pptgen":
            cmd.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    out_root = (args.out_root or root).resolve()
    try:
        if args.command in {"weekly", "pipeline"}:
            weekly_path, cumulative_path, report = run_weekly(root, args.project_id, args.week, out_root, args.mode)
            print(f"weekly: {weekly_path}\ncumulative: {cumulative_path}\n검증 보고서: {report}")
        if args.command in {"pptgen", "pipeline"}:
            template = find_template(root, args.template)
            output = getattr(args, "output", None) or out_root / f"output/{args.project_id}_{args.week}.pptx"
            notes = generate_ppt(
                root, root / f"data/master/projects/{args.project_id}.json",
                _derived_input("weekly", args.project_id, args.week, out_root, root),
                _derived_input("cumulative", args.project_id, args.week, out_root, root),
                template, output, mode=args.mode,
            )
            print(f"템플릿: {template}\nPPT: {output}\nPPT 검사: {output.with_name(output.stem + '_ppt_check.txt')}")
            problems = [n for n in notes if n.startswith("PPT 검사 문제")]
            print(f"PPT 재검사: {'문제 ' + str(len(problems)) + '건' if problems else '통과'}")
    except (FileNotFoundError, ValidationError, BudgetError, AIError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
