from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.warehouses.schemas import (
    CreateWarehouseRequest,
    WarehouseListResponse,
    WarehouseResponse,
)
from app.modules.warehouses.use_cases import (
    InvalidWarehouseCursorError,
    WarehouseCodeConflictError,
    create_warehouse,
    list_warehouses,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/warehouses", tags=["warehouses"]
)


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
def create_warehouse_endpoint(
    payload: CreateWarehouseRequest,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> WarehouseResponse | Response:
    try:
        warehouse = create_warehouse(engine, membership, payload.code, payload.name)
    except WarehouseCodeConflictError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="WAREHOUSE_CODE_CONFLICT",
            message="A warehouse with this code already exists in the organization.",
        )
    return WarehouseResponse(**warehouse.__dict__)


@router.get("", response_model=WarehouseListResponse)
def list_warehouses_endpoint(
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
    include_inactive: bool = False,
) -> WarehouseListResponse | Response:
    try:
        page = list_warehouses(engine, membership, limit, cursor, include_inactive)
    except InvalidWarehouseCursorError:
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="The warehouse cursor is invalid for this organization and filter.",
        )
    return WarehouseListResponse(
        items=[item.__dict__ for item in page.items],
        next_cursor=page.next_cursor,
    )
