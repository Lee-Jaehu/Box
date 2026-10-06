"""Worklog 서버 실행 진입점. 실행.bat 이 선택한 Python 으로 호출한다.

- 서버 종료(Ctrl+C/창 닫기) 후 자동 재시작은 하지 않는다. 오류가 나면 원인을 출력하고 종료한다.
- 방화벽/네트워크 설정은 변경하지 않는다. 접속 가능한 주소만 안내한다.
"""
from __future__ import annotations

import logging
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import load_settings  # noqa: E402


def lan_addresses() -> list[str]:
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def main() -> int:
    settings = load_settings()
    settings.ensure_dirs()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(settings.logs_dir / "worklog.log", encoding="utf-8")])
    import uvicorn

    print("=" * 60)
    print(" Worklog 서버를 시작합니다. 이 창을 닫거나 Ctrl+C 를 누르면 서버가 종료됩니다.")
    print(f" 이 PC에서:      http://localhost:{settings.port}/")
    if settings.host in ("0.0.0.0", "::"):
        for ip in lan_addresses():
            print(f" 다른 PC에서:    http://{ip}:{settings.port}/   (사내망, Windows 방화벽 허용 필요)")
    else:
        print(f" 바인딩 주소:    {settings.host} (이 PC 전용 설정)")
    print(f" 데이터 폴더:    {settings.data_dir}")
    if settings.ai_live:
        print(f" AI 연결:        서버 AI ({settings.ai_model or '모델 미지정'}) — 보고자료를 서버가 바로 만든다")
    else:
        print(f" AI 연결:        설정 없음 → 붙여넣기 방식 ({settings.ai_paste_reason})")
    print("=" * 60, flush=True)
    uvicorn.run("app.main:app_factory", factory=True, host=settings.host, port=settings.port, workers=1,
                log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
