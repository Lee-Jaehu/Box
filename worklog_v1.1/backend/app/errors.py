"""API 오류. 응답 형태: {error:{code,message,fieldErrors?,currentRevision?,resourceId?},requestId}"""
from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, *, field_errors: list[dict[str, str]] | None = None,
                 current_revision: int | None = None, resource_id: str | None = None,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field_errors = field_errors
        self.current_revision = current_revision
        self.resource_id = resource_id
        self.extra = extra

    def body(self, request_id: str) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field_errors:
            err["fieldErrors"] = self.field_errors
        if self.current_revision is not None:
            err["currentRevision"] = self.current_revision
        if self.resource_id:
            err["resourceId"] = self.resource_id
        if self.extra:
            err.update(self.extra)
        return {"error": err, "requestId": request_id}


def not_found(what: str, resource_id: str | None = None) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what}을(를) 찾을 수 없습니다.", resource_id=resource_id)


def conflict(code: str, message: str, **kw: Any) -> ApiError:
    return ApiError(409, code, message, **kw)


def validation(message: str, field_errors: list[dict[str, str]] | None = None) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, field_errors=field_errors)
