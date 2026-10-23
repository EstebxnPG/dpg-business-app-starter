from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.inventory.schemas import (
    MovementHistoryResponse,
    MovementResponse,
    RecordMovementRequest,
    StockBalanceResponse,
    StockTransferResponse,
    TransferStockRequest,
)
from app.modules.inventory.service import (
    IdempotencyConflictError,
    InactiveInventoryContextError,
    InsufficientStockError,
    SameWarehouseTransferError,
)
from app.modules.inventory.use_cases import (
    InvalidMovementCursorError,
    InventoryContextNotFoundError,
    RecordManualMovementCommand,
    TransferInventoryCommand,
    get_stock_position,
    list_stock_movements,
    record_manual_stock_movement,
    transfer_inventory,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/inventory", tags=["inventory"]
)


def inventory_context_not_found(request: Request) -> Response:
    return error_response(
        request,
        status_code=status.HTTP_404_NOT_FOUND,
        code="INVENTORY_CONTEXT_NOT_FOUND",
        message="The product or warehouse is unavailable in this organization.",
    )


@router.post(
    "/movements",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "The member lacks the required permission"},
        404: {"description": "The product or warehouse is unavailable"},
        409: {"description": "Stock or idempotency conflict"},
        503: {"description": "The database is unavailable"},
    },
)
def create_movement(
    organization_id: UUID,
    payload: RecordMovementRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> MovementResponse | Response:
    command = RecordManualMovementCommand(
        organization_id=organization_id,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        reason=payload.reason,
        reference=payload.reference,
        idempotency_key=idempotency_key,
    )

    try:
        result = record_manual_stock_movement(engine, membership, command)
    except InventoryContextNotFoundError:
        return inventory_context_not_found(request)
    except InactiveInventoryContextError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="INVENTORY_CONTEXT_INACTIVE",
            message="The product and warehouse must be active for new movements.",
        )
    except InsufficientStockError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="INSUFFICIENT_STOCK",
            message="There is not enough stock to complete this issue.",
            details={"requested": str(payload.quantity)},
        )
    except IdempotencyConflictError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="The idempotency key was already used with different data.",
        )
    except IntegrityError as error:
        constraint = error.orig.diag.constraint_name
        if constraint == "fk_stock_movements_performer_membership":
            return error_response(
                request,
                status_code=status.HTTP_403_FORBIDDEN,
                code="ACTOR_NOT_MEMBER",
                message="The user cannot perform movements in this organization.",
            )
        return inventory_context_not_found(request)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return MovementResponse(
        movement_id=result.movement_id,
        balance=result.balance,
        replayed=result.replayed,
    )


@router.post(
    "/transfers",
    response_model=StockTransferResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "The member lacks the required permission"},
        404: {"description": "The product or warehouse is unavailable"},
        409: {"description": "Stock, warehouse, or idempotency conflict"},
        503: {"description": "The database is unavailable"},
    },
)
def create_transfer(
    organization_id: UUID,
    payload: TransferStockRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> StockTransferResponse | Response:
    try:
        result = transfer_inventory(
            engine,
            membership,
            TransferInventoryCommand(
                organization_id=organization_id,
                product_id=payload.product_id,
                source_warehouse_id=payload.source_warehouse_id,
                destination_warehouse_id=payload.destination_warehouse_id,
                quantity=payload.quantity,
                reason=payload.reason,
                reference=payload.reference,
                idempotency_key=idempotency_key,
            ),
        )
    except InventoryContextNotFoundError:
        return inventory_context_not_found(request)
    except InactiveInventoryContextError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="INVENTORY_CONTEXT_INACTIVE",
            message="The product and both warehouses must be active.",
        )
    except InsufficientStockError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="INSUFFICIENT_STOCK",
            message="There is not enough stock to complete this transfer.",
            details={"requested": str(payload.quantity)},
        )
    except SameWarehouseTransferError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="SAME_WAREHOUSE_TRANSFER",
            message="Source and destination warehouses must differ.",
        )
    except IdempotencyConflictError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_KEY_REUSED",
            message="The idempotency key was already used with different data.",
        )
    except IntegrityError as error:
        if error.orig.diag.constraint_name == "fk_stock_transfers_performer_membership":
            return error_response(
                request,
                status_code=status.HTTP_403_FORBIDDEN,
                code="ACTOR_NOT_MEMBER",
                message="The user cannot transfer stock in this organization.",
            )
        return inventory_context_not_found(request)

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return StockTransferResponse(
        transfer_id=result.transfer_id,
        source_balance=result.source_balance,
        destination_balance=result.destination_balance,
        replayed=result.replayed,
    )


@router.get(
    "/stock/{product_id}/warehouses/{warehouse_id}",
    response_model=StockBalanceResponse,
)
def read_stock_position(
    product_id: UUID,
    warehouse_id: UUID,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> StockBalanceResponse | Response:
    try:
        position = get_stock_position(engine, membership, product_id, warehouse_id)
    except InventoryContextNotFoundError:
        return inventory_context_not_found(request)
    return StockBalanceResponse(**position.__dict__)


@router.get("/movements", response_model=MovementHistoryResponse)
def read_movement_history(
    product_id: UUID,
    warehouse_id: UUID,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> MovementHistoryResponse | Response:
    try:
        page = list_stock_movements(
            engine,
            membership,
            product_id,
            warehouse_id,
            limit,
            cursor,
        )
    except InventoryContextNotFoundError:
        return inventory_context_not_found(request)
    except InvalidMovementCursorError:
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="The movement cursor is invalid for this inventory context.",
        )
    return MovementHistoryResponse(
        items=[item.__dict__ for item in page.items],
        next_cursor=page.next_cursor,
    )
