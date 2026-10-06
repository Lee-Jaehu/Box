"""백엔드 테스트 공통: backend 폴더(app, weekly_report 패키지)를 import 경로에 넣는다."""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture(autouse=True)
def _no_ai_pacing(monkeypatch):
    """요청 간격 조절(초당 1회 한도 대응)은 실제로 기다리므로 테스트에서는 끈다. 간격 자체는 test_ai_pacing에서 따로 확인."""
    from weekly_report import ai

    monkeypatch.setattr(ai.ExaoneClient, "_pace", lambda self: None)
