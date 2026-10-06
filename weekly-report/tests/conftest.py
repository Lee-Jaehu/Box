import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "주간업무PPT_Template_v2.pptx"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def repo(tmp_path) -> Path:
    """저장소 입력(설정·스키마·프롬프트·예시 데이터)의 임시 복사본. 원본 예시를 덮어쓰지 않는다."""
    copy = tmp_path / "repo"
    copy.mkdir()
    for name in ("config", "schemas", "prompts", "data"):
        shutil.copytree(ROOT / name, copy / name)
    shutil.copy(TEMPLATE, copy / TEMPLATE.name)
    return copy


@pytest.fixture(autouse=True)
def _no_ai_pacing(monkeypatch):
    """요청 간격 조절(초당 1회 한도 대응)은 실제로 기다리므로 테스트에서는 끈다. 간격 자체는 test_ai_pacing에서 따로 확인."""
    from weekly_report import ai

    monkeypatch.setattr(ai.ExaoneClient, "_pace", lambda self: None)
