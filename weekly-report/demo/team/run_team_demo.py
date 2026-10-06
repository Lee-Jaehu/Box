"""팀 주간보고 데모: 팀 요약 페이지(EXAONE 요약 JSON → Rule 배치) + 과제별 주간 장표를 한 파일로.

사용법 (weekly-report 폴더에서):
    python demo/team/run_team_demo.py

- 조립자동보정팀 2026-W40: P-ASM-001 (W40 데모 Daily·결과 사용) → 요약 1장 + 주간 장표
- 검증팀 2026-W39: 합성 5과제(fixtures) → 한 장에 5과제 요약 + 주간 장표 5장
- 임시 root를 만든다 (저장소 data/는 건드리지 않음).
- EXAONE 대신 쓰는 project_summary 응답은 demo/team/mock_responses/ (Claude가 프롬프트를 읽고 입력 근거만으로 작성).
  실제 EXAONE에 보낼 프롬프트 전문은 demo/team/prompts_sent/에 남는다. 응답이 없으면 프롬프트만 남기고 멈춘다.
- 결과: demo/team/out/ (pptx, *_check.txt, summary JSON·검증 보고서, preview/*.png)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

DEMO = Path(__file__).resolve().parent
REPO = DEMO.parents[1]
sys.path.insert(0, str(REPO))

from weekly_report.ai import ExaoneClient, MockResponseMissing  # noqa: E402
from weekly_report.pptgen import find_template  # noqa: E402
from weekly_report.preview import PreviewError, render_preview  # noqa: E402
from weekly_report.team import generate_team_deck  # noqa: E402

FIXTURES = REPO / "fixtures/weekly-report-fixture-kit"
FIXTURE_PROJECTS = ("P-APC-101", "P-ROL-102", "P-INV-103", "P-SYS-104", "P-DAT-105")
RUNS = (("조립자동보정팀", "2026-W40"), ("검증팀", "2026-W39"))


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


def build_root(tmp: Path) -> Path:
    root = tmp / "root"
    for name in ("config", "schemas", "data"):
        shutil.copytree(REPO / name, root / name)
    shutil.copytree(REPO / "prompts", root / "prompts")
    mocks = root / "prompts/mock_responses"
    for folder in (REPO / "demo/w40/mock_responses", FIXTURES / "fixture-root/prompts/mock_responses", DEMO / "mock_responses"):
        for path in folder.glob("*.json"):
            shutil.copy(path, mocks / path.name)
    # 조립자동보정팀 W40: 데모 Daily + 데모 결과(weekly/cumulative)
    shutil.copytree(REPO / "demo/w40/raw", root / "data/raw", dirs_exist_ok=True)
    shutil.copytree(REPO / "demo/w40/out/data/derived", root / "data/derived", dirs_exist_ok=True)
    # 검증팀 W39: 합성 5과제 기준정보 + Daily + fixtures 결과
    shutil.copytree(FIXTURES / "fixture-root/data/raw", root / "data/raw", dirs_exist_ok=True)
    for pid in FIXTURE_PROJECTS:
        shutil.copy(FIXTURES / f"fixture-root/data/master/projects/{pid}.json", root / f"data/master/projects/{pid}.json")
        shutil.copytree(FIXTURES / f"results/{pid}/data/derived", root / "data/derived", dirs_exist_ok=True)
    for path in [*REPO.glob("LGSM*.[tT][tT][fF]"), find_template(REPO)]:
        (root / path.name).symlink_to(path)
    return root


def main() -> int:
    out = DEMO / "out"
    sent = DEMO / "prompts_sent"
    for folder in (out, sent):
        shutil.rmtree(folder, ignore_errors=True)
    with tempfile.TemporaryDirectory(prefix="team-demo-") as tmp:
        root = build_root(Path(tmp))
        client = RecordingClient(root, sent)
        for team, week in RUNS:
            output = out / f"팀주간보고_{team}_{week}.pptx"
            try:
                result = generate_team_deck(root, team, week, output, out_root=out, client=client)
            except MockResponseMissing as exc:
                print(f"응답 대기: {exc}\n→ {sent}의 프롬프트를 보고 {DEMO / 'mock_responses'}에 응답을 넣은 뒤 다시 실행")
                return 2
            print(f"PPT: {output.relative_to(DEMO)} / 검사: {result.check.relative_to(DEMO)}")
            print("  " + "\n  ".join(result.notes))
            print("  재검사: " + ("; ".join(result.problems) or "통과"))
            try:
                images, _ = render_preview(root, output, out / "preview")
                print("  미리보기: " + ", ".join(p.name for p in images))
            except PreviewError as exc:
                print(f"  미리보기 생략: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
