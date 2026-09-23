from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.core.authorization import OrganizationNotFoundError, PermissionDeniedError
from app.core.errors import error_response
from app.core.security import InvalidCredentialsError
from app.database import database_ready
from app.modules.auth.router import router as auth_router
from app.modules.inventory.router import router as inventory_router

app = FastAPI(title="DPG Business App Starter", version="0.1.0")
app.include_router(auth_router)
app.include_router(inventory_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    return error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="The request contains invalid data.",
        details=jsonable_encoder(error.errors()),
    )


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(
    request: Request, error: InvalidCredentialsError
) -> JSONResponse:
    response = error_response(
        request,
        status_code=401,
        code="INVALID_CREDENTIALS",
        message="The credentials are invalid or expired.",
    )
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


@app.exception_handler(OrganizationNotFoundError)
async def organization_not_found_handler(
    request: Request, error: OrganizationNotFoundError
) -> JSONResponse:
    return error_response(
        request,
        status_code=404,
        code="ORGANIZATION_NOT_FOUND",
        message="The organization is unavailable.",
    )


@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(
    request: Request, error: PermissionDeniedError
) -> JSONResponse:
    return error_response(
        request,
        status_code=403,
        code="PERMISSION_DENIED",
        message="The user cannot perform this action.",
        details={"required_permission": error.permission},
    )


@app.exception_handler(OperationalError)
async def database_unavailable_handler(
    request: Request, error: OperationalError
) -> JSONResponse:
    return error_response(
        request,
        status_code=503,
        code="DATABASE_UNAVAILABLE",
        message="The service is temporarily unavailable.",
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready() -> JSONResponse:
    if not database_ready():
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ok"})
