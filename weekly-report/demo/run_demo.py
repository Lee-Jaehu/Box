"""데모 실행: 저장소 입력 + 데모 Daily → weekly/cumulative JSON → PPT → 미리보기 PNG.

사용법 (weekly-report 폴더에서):
    python demo/run_demo.py demo/w40 P-ASM-001 2026-W40

- 저장소의 data/master·data/raw·data/derived는 건드리지 않는다. 임시 root에 복사한 뒤 데모 Daily를 더한다.
- EXAONE 대신 쓰는 응답은 `{데모}/mock_responses/`에 둔다 (현재는 Claude가 프롬프트를 읽고 작성한 응답).
- 실제로 EXAONE에 보낼 프롬프트 전문은 `{데모}/prompts_sent/`에 남긴다. 응답 파일이 없으면 프롬프트만 남기고 멈춘다.
- 결과: `{데모}/out/` (data/derived/…, output/…pptx, output/preview/…png, 검증·검사 보고서)
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from weekly_report.ai import ExaoneClient, MockResponseMissing  # noqa: E402
from weekly_report.pptgen import find_template, generate_ppt  # noqa: E402
from weekly_report.preview import PreviewError, render_preview  # noqa: E402
from weekly_report.weekly import run_weekly  # noqa: E402


class RecordingClient(ExaoneClient):
    """mock 응답을 쓰되, 보낼 프롬프트 전문을 파일로 남긴다."""

    def __init__(self, root: Path, sent_dir: Path):
        super().__init__(root, "mock")
        self.sent_dir = sent_dir

    def complete(self, prompt_id, project_id, week, system, user, variant=None):
        name = f"{prompt_id}__{project_id}__{week}" + (f"__{variant}" if variant else "")
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        (self.sent_dir / f"{name}.txt").write_text(f"===== SYSTEM =====\n{system}\n\n===== USER =====\n{user}\n", encoding="utf-8")
        return super().complete(prompt_id, project_id, week, system, user, variant)


def build_root(demo: Path, tmp: Path) -> Path:
    root = tmp / "root"
    for name in ("config", "schemas", "data"):
        shutil.copytree(REPO / name, root / name)
    (root / "prompts").mkdir(parents=True)
    for path in (REPO / "prompts").glob("*.*"):
        shutil.copy(path, root / "prompts" / path.name)
    shutil.copytree(REPO / "prompts/mock_responses", root / "prompts/mock_responses")
    if (demo / "mock_responses").is_dir():
        for path in (demo / "mock_responses").glob("*.json"):
            shutil.copy(path, root / "prompts/mock_responses" / path.name)
    if (demo / "raw").is_dir():
        shutil.copytree(demo / "raw", root / "data/raw", dirs_exist_ok=True)
    for path in [*REPO.glob("LGSM*.[tT][tT][fF]"), find_template(REPO)]:
        (root / path.name).symlink_to(path)  # 글꼴·템플릿 (누적 요약 한도 계산과 PPT 생성에 사용)
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("demo", type=Path)
    parser.add_argument("project_id")
    parser.add_argument("week")
    args = parser.parse_args()
    demo = args.demo.resolve()
    out = demo / "out"
    with tempfile.TemporaryDirectory(prefix="wr-demo-") as tmp:
        root = build_root(demo, Path(tmp))
        shutil.rmtree(demo / "prompts_sent", ignore_errors=True)  # 이번 실행에서 보낸 프롬프트만 남긴다
        client = RecordingClient(root, demo / "prompts_sent")
        try:
            weekly_path, cum_path, report = run_weekly(root, args.project_id, args.week, out, client=client)
        except MockResponseMissing as exc:
            print(f"응답 대기: {exc}\n→ {demo / 'prompts_sent'}의 프롬프트를 보고 {demo / 'mock_responses'}에 응답을 넣은 뒤 다시 실행")
            return 2
        print(f"weekly: {weekly_path.relative_to(demo)}\ncumulative: {cum_path.relative_to(demo)}\n검증 보고서: {report.relative_to(demo)}")
        pptx = out / f"output/{args.project_id}_{args.week}.pptx"
        notes = generate_ppt(root, root / f"data/master/projects/{args.project_id}.json", weekly_path, cum_path,
                             find_template(REPO), pptx, client=client)
        problems = [n for n in notes if n.startswith("PPT 검사 문제")]
        print(f"PPT: {pptx.relative_to(demo)} (재검사 {'문제 ' + str(len(problems)) + '건' if problems else '통과'})")
        try:
            images, preview_notes = render_preview(root, pptx, out / "output/preview")
            print(*preview_notes, *(f"미리보기: {p.relative_to(demo)}" for p in images), sep="\n")
        except PreviewError as exc:
            print(f"미리보기 생략: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
