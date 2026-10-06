"""FastAPI 앱 팩토리. 같은 Origin 에서 /api/v1 과 빌드된 화면(frontend/dist)을 함께 제공한다."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from .api.common import error_body
from .api.routes import router
from .config import Settings, load_settings
from .errors import ApiError
from .runtime import Runtime, build_runtime
from .workers import start_worker

log = logging.getLogger("worklog")

try:  # 보고자료(PPT)는 python-pptx 등 추가 패키지가 필요하다. 없으면 그 기능만 끄고 나머지 서비스는 정상 실행한다.
    from .api.reports import router as reports_router
    from .services.reports import start_report_worker
    REPORTS_IMPORT_ERROR: str | None = None
except ImportError as _exc:  # pragma: no cover - 패키지 미설치 환경
    REPORTS_IMPORT_ERROR = str(_exc)
    start_report_worker = None
    from fastapi import APIRouter

    reports_router = APIRouter(prefix="/api/v1/reports")

    @reports_router.api_route("/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
    def _reports_unavailable(request: Request, rest: str):
        err = ApiError(503, "REPORTS_UNAVAILABLE", "보고자료 기능에 필요한 패키지가 서버에 없습니다. 관리자가 "
                       "`pip install -r backend/requirements.txt` 로 설치한 뒤 서버를 다시 시작해야 합니다.")
        return JSONResponse(status_code=503, content=error_body(err, request))


def _field_path(loc: tuple) -> str:
    parts = [p for p in loc if p not in ("body", "query", "path")]
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "body"


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        rt = runtime or build_runtime(settings)
        app.state.rt = rt
        thread = start_worker(rt) if rt.settings.export_worker_enabled else None
        # 보고자료(PPT)는 AI 호출이 길 수 있어 별도 스레드 (export·백업 작업을 막지 않게)
        report_thread = (start_report_worker(rt) if start_report_worker and rt.settings.export_worker_enabled
                         and rt.settings.report_worker_enabled else None)
        if REPORTS_IMPORT_ERROR:
            log.warning("보고자료 기능 꺼짐 (패키지 없음: %s). pip install -r backend/requirements.txt", REPORTS_IMPORT_ERROR)
        try:
            yield
        finally:
            rt.stop_event.set()
            for t in (thread, report_thread):
                if t:
                    t.join(timeout=10)
            rt.dispose_engines()

    app = FastAPI(title="Worklog", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=error_body(exc, request))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"field": _field_path(tuple(e["loc"])), "code": e["type"], "message": e["msg"]} for e in exc.errors()]
        err = ApiError(422, "VALIDATION_ERROR", "요청 형식이 올바르지 않습니다.", field_errors=fields)
        return JSONResponse(status_code=422, content=error_body(err, request))

    @app.exception_handler(OperationalError)
    async def db_busy(request: Request, exc: OperationalError):
        msg = str(exc.orig).lower() if getattr(exc, "orig", None) else ""
        if "locked" in msg or "busy" in msg:
            err = ApiError(503, "STORAGE_BUSY", "저장소가 잠시 바쁩니다. 같은 요청을 다시 시도해 주세요.", extra={"retryable": True})
            return JSONResponse(status_code=503, content=error_body(err, request), headers={"Retry-After": "1"})
        log.exception("database error request=%s", request.state.request_id)
        err = ApiError(500, "DATABASE_ERROR", "저장 중 오류가 발생했습니다.")
        return JSONResponse(status_code=500, content=error_body(err, request))

    @app.exception_handler(IntegrityError)
    async def integrity(request: Request, exc: IntegrityError):
        log.warning("integrity error request=%s: %s", request.state.request_id, exc.orig)
        err = ApiError(409, "INTEGRITY_CONFLICT", "다른 곳에서 먼저 변경되어 저장할 수 없습니다. 새로고침 후 다시 시도해 주세요.")
        return JSONResponse(status_code=409, content=error_body(err, request))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error request=%s", request.state.request_id)  # 본문/경로는 응답에 노출하지 않는다
        err = ApiError(500, "INTERNAL_ERROR", "서버 오류가 발생했습니다.")
        return JSONResponse(status_code=500, content=error_body(err, request))

    app.include_router(router)
    app.include_router(reports_router)
    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "알 수 없는 API 경로입니다."}})
        if not index.exists():
            return JSONResponse({"message": "화면 빌드(frontend/dist)가 없습니다. 개발 PC에서 `npm run build` 후 배포하세요."}, status_code=200)
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and (candidate == root or root in candidate.parents):
            return FileResponse(candidate)
        # index.html 은 항상 재검증해 업데이트 후 옛 번들(해시 파일명)을 가리키지 않게 한다. assets/* 는 해시 파일명이라 캐시해도 안전.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})  # SPA fallback. data 폴더는 정적 경로로 노출하지 않는다.


def app_factory() -> FastAPI:  # uvicorn --factory 진입점
    return create_app()
