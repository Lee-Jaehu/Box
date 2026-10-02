from __future__ import annotations

import argparse
from pathlib import Path

from .pptgen import generate_ppt
from .weekly import run_weekly


def main() -> None:
    parser = argparse.ArgumentParser(description="주간업무 자동화 시연 CLI")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    weekly = sub.add_parser("weekly"); weekly.add_argument("project_id"); weekly.add_argument("week"); weekly.add_argument("--mode", choices=("mock", "live"), default="mock"); weekly.add_argument("--out-root", type=Path)
    ppt = sub.add_parser("pptgen"); ppt.add_argument("project_id"); ppt.add_argument("week"); ppt.add_argument("--template", type=Path); ppt.add_argument("--output", type=Path)
    pipeline = sub.add_parser("pipeline"); pipeline.add_argument("project_id"); pipeline.add_argument("week"); pipeline.add_argument("--mode", choices=("mock", "live"), default="mock"); pipeline.add_argument("--out-root", type=Path)
    args = parser.parse_args(); root = args.root.resolve()
    if args.command in {"weekly", "pipeline"}:
        out = (args.out_root or root).resolve(); paths = run_weekly(root, args.project_id, args.week, out, args.mode); print(*(str(p) for p in paths), sep="\n")
    if args.command in {"pptgen", "pipeline"}:
        out_root = (getattr(args, "out_root", None) or root).resolve()
        template = getattr(args, "template", None) or root / "templates/주간업무PPT_Template_v2.pptx"
        output = getattr(args, "output", None) or out_root / f"output/{args.project_id}_{args.week}.pptx"
        warnings = generate_ppt(root, root / f"data/master/projects/{args.project_id}.json", out_root / f"data/derived/weekly/{args.project_id}/{args.week}.json", out_root / f"data/derived/cumulative/{args.project_id}/{args.week}.json", template, output)
        print(output); print(*(f"경고: {w}" for w in warnings), sep="\n")


if __name__ == "__main__": main()
