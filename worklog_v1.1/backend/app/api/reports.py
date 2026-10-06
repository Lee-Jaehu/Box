"""보고자료(PPT) 생성 API. 작업은 서버 작업 스레드가 처리하고, 화면은 상태를 주기적으로 조회한다."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import schemas as sc
from ..services import reports as rep
from ..services.common import load_actor
from .common import mutate, request_id, rt_of

router = APIRouter(prefix="/api/v1/reports")


def _ok(request: Request, data, code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=code, content={"data": data, "meta": {"requestId": request_id(request)}})


@router.get("/config")
def report_config(request: Request):
    return _ok(request, rep.config_info(rt_of(request).settings))


@router.get("/jobs")
def list_jobs(request: Request, limit: int = 30):
    jobs = rep.JobStore(rt_of(request).settings).all()[: max(1, min(limit, 100))]
    return _ok(request, {"items": [rep.public(j) for j in jobs]})


@router.post("/jobs")
def create_job(request: Request, body: sc.ReportJobCreate):
    st = rt_of(request).settings

    def fn(s, actor_id):
        return rep.create_job(s, st, load_actor(s, actor_id), body)

    code, resp = mutate(request, body.model_dump(mode="json"), fn, status_code=202)
    return JSONResponse(status_code=code, content=resp)


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    return _ok(request, rep.public(rep.JobStore(rt_of(request).settings).require(job_id), full=True))


@router.post("/jobs/{job_id}/response")
def post_response(request: Request, job_id: str, body: sc.ReportResponse):
    rt = rt_of(request)
    with rt.read_factory() as s:
        actor = load_actor(s, request.headers.get("X-Actor-Id"))
    return _ok(request, rep.submit_response(rt.settings, job_id, body.response_name, body.text, actor))


@router.post("/jobs/{job_id}/retry")
def retry(request: Request, job_id: str):
    rt = rt_of(request)
    with rt.read_factory() as s:
        load_actor(s, request.headers.get("X-Actor-Id"))
    return _ok(request, rep.retry_job(rt.settings, job_id), 202)


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: str):
    rt = rt_of(request)
    with rt.read_factory() as s:
        load_actor(s, request.headers.get("X-Actor-Id"))
    return _ok(request, rep.cancel_job(rt.settings, job_id))


@router.get("/jobs/{job_id}/files/{name}")
def download(request: Request, job_id: str, name: str):
    path = rep.job_file(rt_of(request).settings, job_id, name)
    media = ("application/vnd.openxmlformats-officedocument.presentationml.presentation" if path.suffix == ".pptx"
             else "text/plain; charset=utf-8")
    return FileResponse(path, media_type=media,
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}", "Cache-Control": "no-store"})
