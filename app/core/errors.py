from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": details if details is not None else {},
            "request_id": request.state.request_id,
        },
    )
