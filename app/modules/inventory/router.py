from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.inventory.schemas import MovementResponse, RecordMovementRequest
from app.modules.inventory.service import (
    IdempotencyConflictError,
    InsufficientStockError,
)
from app.modules.inventory.use_cases import (
    RecordManualMovementCommand,
    record_manual_stock_movement,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/inventory", tags=["inventory"]
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
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVENTORY_CONTEXT_NOT_FOUND",
            message="The product or warehouse is unavailable in this organization.",
        )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return MovementResponse(
        movement_id=result.movement_id,
        balance=result.balance,
        replayed=result.replayed,
    )
