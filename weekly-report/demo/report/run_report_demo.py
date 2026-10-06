"""보고 자료 데모: 경영진 1장 요약(P-ASM-001, W40) + 월간 종합 보고(’26.9월, 6개 과제) → PPT·미리보기 PNG.

사용법 (weekly-report 폴더에서):
    python demo/report/run_report_demo.py

- 임시 root를 만든다: 저장소 입력 + W40 데모 결과(demo/w40/out) + 합성 5과제(fixtures 결과 W39).
  저장소 data/는 건드리지 않는다.
- EXAONE 대신 쓰는 응답은 demo/report/mock_responses/ (Claude가 프롬프트를 읽고 입력 근거만으로 작성).
- 실제 EXAONE에 보낼 프롬프트 전문은 demo/report/prompts_sent/에 남긴다. 응답이 없으면 프롬프트만 남기고 멈춘다.
- 결과: demo/report/out/ (pptx, *_check.txt, preview/*.png)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

DEMO = Path(__file__).resolve().parent
REPO = DEMO.parents[1]
sys.path.insert(0, str(REPO))

from weekly_report.ai import ExaoneClient, MockResponseMissing  # noqa: E402
from weekly_report.preview import PreviewError, render_preview  # noqa: E402
from weekly_report.report.generate import generate_exec_summary, generate_monthly  # noqa: E402
from weekly_report.report.render import TEMPLATE_NAME  # noqa: E402

FIXTURES = REPO / "fixtures/weekly-report-fixture-kit"
FIXTURE_PROJECTS = ("P-APC-101", "P-ROL-102", "P-INV-103", "P-SYS-104", "P-DAT-105")
TODAY = date(2026, 10, 4)


class RecordingClient(ExaoneClient):
    """mock 응답을 쓰되, 보낼 프롬프트 전문을 파일로 남긴다."""

    def __init__(self, root: Path, sent_dir: Path):
        super().__init__(root, "mock", mock_dir=DEMO / "mock_responses")
        self.sent_dir = sent_dir

    def complete(self, prompt_id, project_id, week, system, user, variant=None):
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        (self.sent_dir / f"{prompt_id}__{project_id}__{week}.txt").write_text(
            f"===== SYSTEM =====\n{system}\n\n===== USER =====\n{user}\n", encoding="utf-8")
        return super().complete(prompt_id, project_id, week, system, user, variant)


def build_root(tmp: Path) -> Path:
    root = tmp / "root"
    for name in ("config", "schemas", "prompts"):
        shutil.copytree(REPO / name, root / name)
    shutil.copytree(REPO / "data/master", root / "data/master")
    shutil.copytree(REPO / "data/derived", root / "data/derived")
    shutil.copytree(REPO / "demo/w40/out/data/derived", root / "data/derived", dirs_exist_ok=True)
    for pid in FIXTURE_PROJECTS:  # 합성 과제: 기준정보 + W39 결과
        shutil.copy(FIXTURES / f"fixture-root/data/master/projects/{pid}.json", root / f"data/master/projects/{pid}.json")
        shutil.copytree(FIXTURES / f"results/{pid}/data/derived", root / "data/derived", dirs_exist_ok=True)
    for path in [*REPO.glob("LGSM*.[tT][tT][fF]"), REPO / TEMPLATE_NAME]:
        (root / path.name).symlink_to(path)
    return root


def main() -> int:
    out = DEMO / "out"
    if out.exists():
        shutil.rmtree(out)
    sent = DEMO / "prompts_sent"
    if sent.exists():
        shutil.rmtree(sent)
    with tempfile.TemporaryDirectory(prefix="report-demo-") as tmp:
        root = build_root(Path(tmp))
        client = RecordingClient(root, sent)
        results = []
        try:
            results.append(generate_exec_summary(root, "P-ASM-001", "2026-W40", out / "경영진요약_P-ASM-001_2026-W40.pptx",
                                                 client=client, today=TODAY))
            results.append(generate_monthly(root, ["P-ASM-001", *FIXTURE_PROJECTS], 2026, 9,
                                            out / "월간종합_2026-09.pptx", client=client, today=TODAY))
        except MockResponseMissing as exc:
            print(f"응답 없음: {exc}\n프롬프트: {sent} (EXAONE에 보낸 뒤 응답을 {DEMO / 'mock_responses'}에 저장)")
            return 1
        for result in results:
            print(f"PPT: {result['pptx'].relative_to(DEMO)} / 검사: {result['check'].relative_to(DEMO)}")
            print("  AI 응답 처리: " + "; ".join(result["notes"]))
            print("  재검사: " + ("; ".join(result["problems"]) or "통과"))
            try:
                images, _ = render_preview(root, result["pptx"], out / "preview")
                print("  미리보기: " + ", ".join(p.name for p in images))
            except PreviewError as exc:
                print(f"  미리보기 생략: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
