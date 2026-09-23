from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Engine, insert, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from app.modules.inventory.models import StockBalance, StockMovement


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"


class InvalidMovementQuantityError(ValueError):
    pass


class InsufficientStockError(ValueError):
    pass


@dataclass(frozen=True)
class RecordMovementCommand:
    organization_id: UUID
    product_id: UUID
    warehouse_id: UUID
    performed_by_id: UUID
    movement_type: MovementType
    quantity: Decimal
    reason: str
    reference: str | None = None


@dataclass(frozen=True)
class MovementResult:
    movement_id: UUID
    balance: Decimal


def record_stock_movement(
    engine: Engine, command: RecordMovementCommand
) -> MovementResult:
    if command.quantity <= 0:
        raise InvalidMovementQuantityError("Movement quantity must be positive")

    with engine.begin() as connection:
        if command.movement_type is MovementType.RECEIPT:
            balance = connection.scalar(
                postgresql_insert(StockBalance)
                .values(
                    organization_id=command.organization_id,
                    product_id=command.product_id,
                    warehouse_id=command.warehouse_id,
                    quantity=command.quantity,
                )
                .on_conflict_do_update(
                    index_elements=[
                        StockBalance.organization_id,
                        StockBalance.product_id,
                        StockBalance.warehouse_id,
                    ],
                    set_={"quantity": StockBalance.quantity + command.quantity},
                )
                .returning(StockBalance.quantity)
            )
        else:
            balance = connection.scalar(
                update(StockBalance)
                .where(
                    StockBalance.organization_id == command.organization_id,
                    StockBalance.product_id == command.product_id,
                    StockBalance.warehouse_id == command.warehouse_id,
                    StockBalance.quantity >= command.quantity,
                )
                .values(quantity=StockBalance.quantity - command.quantity)
                .returning(StockBalance.quantity)
            )
            if balance is None:
                raise InsufficientStockError("Insufficient stock for this issue")

        movement_id = connection.scalar(
            insert(StockMovement)
            .values(
                organization_id=command.organization_id,
                product_id=command.product_id,
                warehouse_id=command.warehouse_id,
                performed_by_id=command.performed_by_id,
                movement_type=command.movement_type.value,
                quantity=command.quantity,
                reason=command.reason,
                reference=command.reference,
            )
            .returning(StockMovement.id)
        )

    return MovementResult(movement_id=movement_id, balance=balance)
