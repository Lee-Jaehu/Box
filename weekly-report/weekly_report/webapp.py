"""로컬 웹 테스트 화면 (표준 라이브러리 http.server, 127.0.0.1 전용).

python -m weekly_report serve  →  http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import mimetypes
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import workbench as wb

INDEX = Path(__file__).resolve().parent / "web/index.html"
_lock = threading.Lock()  # 파일을 쓰는 요청은 한 번에 하나씩


class Handler(BaseHTTPRequestHandler):
    workspace: Path = wb.DEFAULT_WORKSPACE

    def log_message(self, fmt: str, *args: Any) -> None:  # 콘솔에 요청 로그를 남기지 않는다
        return

    # ---------------------------------------------------------------- 응답 도우미
    def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value: Any, status: int = 200) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def _guard(self, action) -> None:
        try:
            with _lock:
                wb.init_workspace(self.workspace)  # 빠진 파일이 있으면 먼저 복구 (초기화 중단 등)
                self._json(action())
        except wb.WorkbenchError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # 화면에는 짧게, 콘솔에는 자세히
            traceback.print_exc()
            self._json({"error": f"처리 중 오류: {type(exc).__name__}: {exc}"}, 500)

    # ---------------------------------------------------------------- 라우팅
    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        ws = self.workspace
        if url.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/projects":
            self._guard(lambda: {"projects": wb.list_projects(ws), "workspace": str(ws)})
        elif url.path == "/api/dailies":
            def dailies():
                rows = wb.list_dailies(ws, query["project_id"], query["week"])
                for row in rows:
                    row["table_title"], row["table_text"] = wb.table_text(row)
                return {"dailies": rows}
            self._guard(dailies)
        elif url.path.startswith("/files/"):
            try:
                path = wb.resolve_file(ws, unquote(url.path[len("/files/"):]))
            except wb.WorkbenchError as exc:
                self._json({"error": str(exc)}, 404)
                return
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix in (".txt", ".json"):
                ctype += "; charset=utf-8"
            extra = {"Content-Disposition": f"attachment; filename*=UTF-8''{path.name}"} if path.suffix == ".pptx" else None
            self._send(200, path.read_bytes(), ctype, extra)
        else:
            self._json({"error": "없는 주소"}, 404)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        ws = self.workspace
        try:
            body = self._body()
        except json.JSONDecodeError:
            self._json({"error": "요청 형식 오류"}, 400)
            return
        routes = {
            "/api/daily": lambda: {"daily": wb.save_daily(ws, body)},
            "/api/daily/delete": lambda: (wb.mark_deleted(ws, body["daily_id"]), {"ok": True})[1],
            "/api/run": lambda: wb.run(ws, body["project_id"], body["week"], body.get("mode", "mock")),
            "/api/response": lambda: (wb.save_response(ws, body["name"], body["text"]), {"ok": True})[1],
            "/api/responses/clear": lambda: {"removed": wb.clear_responses(ws, body["project_id"], body["week"])},
            "/api/reset": lambda: wb.init_workspace(ws, force=True),
        }
        action = routes.get(url.path)
        if action is None:
            self._json({"error": "없는 주소"}, 404)
            return
        self._guard(action)


def make_server(workspace: Path, port: int = 8765) -> ThreadingHTTPServer:
    wb.init_workspace(workspace)
    handler = type("WorkbenchHandler", (Handler,), {"workspace": workspace.resolve()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(workspace: Path, port: int = 8765, open_browser: bool = True) -> None:
    server = make_server(workspace, port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"주간업무 PPT 테스트 화면: {url}\n작업공간: {workspace}\n종료: Ctrl+C")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        server.server_close()
