from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.warehouses.schemas import (
    CreateWarehouseRequest,
    UpdateWarehouseRequest,
    WarehouseListResponse,
    WarehouseResponse,
)
from app.modules.warehouses.use_cases import (
    InvalidWarehouseCursorError,
    WarehouseCodeConflictError,
    WarehouseHasStockError,
    WarehouseNotFoundError,
    create_warehouse,
    get_warehouse,
    list_warehouses,
    update_warehouse,
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
    search: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
) -> WarehouseListResponse | Response:
    try:
        page = list_warehouses(
            engine, membership, limit, cursor, include_inactive, search
        )
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


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
def get_warehouse_endpoint(
    warehouse_id: UUID,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> WarehouseResponse | Response:
    try:
        warehouse = get_warehouse(engine, membership, warehouse_id)
    except WarehouseNotFoundError:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="WAREHOUSE_NOT_FOUND",
            message="The warehouse is unavailable in this organization.",
        )
    return WarehouseResponse(**warehouse.__dict__)


@router.patch("/{warehouse_id}", response_model=WarehouseResponse)
def update_warehouse_endpoint(
    warehouse_id: UUID,
    payload: UpdateWarehouseRequest,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> WarehouseResponse | Response:
    try:
        warehouse = update_warehouse(
            engine, membership, warehouse_id, payload.name, payload.active
        )
    except WarehouseNotFoundError:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="WAREHOUSE_NOT_FOUND",
            message="The warehouse is unavailable in this organization.",
        )
    except WarehouseHasStockError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="WAREHOUSE_HAS_STOCK",
            message="A warehouse with stock cannot be deactivated.",
        )
    return WarehouseResponse(**warehouse.__dict__)
