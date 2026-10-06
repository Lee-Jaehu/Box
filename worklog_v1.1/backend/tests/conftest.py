"""백엔드 테스트 공통: backend 폴더(app, weekly_report 패키지)를 import 경로에 넣는다."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
