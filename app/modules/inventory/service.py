import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

from app.modules.inventory.models import StockBalance, StockMovement


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"


class InvalidMovementQuantityError(ValueError):
    pass


class InsufficientStockError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
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
    idempotency_key: str
    reference: str | None = None


@dataclass(frozen=True)
class MovementResult:
    movement_id: UUID
    balance: Decimal
    replayed: bool


def _request_fingerprint(command: RecordMovementCommand) -> str:
    payload = {
        "organization_id": str(command.organization_id),
        "product_id": str(command.product_id),
        "warehouse_id": str(command.warehouse_id),
        "performed_by_id": str(command.performed_by_id),
        "movement_type": command.movement_type.value,
        "quantity": format(command.quantity.normalize(), "f"),
        "reason": command.reason,
        "reference": command.reference,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _replayed_result(connection, command, fingerprint) -> MovementResult | None:
    existing = connection.execute(
        select(
            StockMovement.id,
            StockMovement.balance_after,
            StockMovement.request_fingerprint,
        ).where(
            StockMovement.organization_id == command.organization_id,
            StockMovement.idempotency_key == command.idempotency_key,
        )
    ).one_or_none()
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflictError(
            "Idempotency key was already used with different movement data"
        )
    return MovementResult(
        movement_id=existing.id,
        balance=existing.balance_after,
        replayed=True,
    )


def record_stock_movement(
    engine: Engine, command: RecordMovementCommand
) -> MovementResult:
    if command.quantity <= 0:
        raise InvalidMovementQuantityError("Movement quantity must be positive")
    if not command.idempotency_key.strip():
        raise ValueError("Idempotency key must not be empty")

    fingerprint = _request_fingerprint(command)

    try:
        with engine.begin() as connection:
            replayed = _replayed_result(connection, command, fingerprint)
            if replayed is not None:
                return replayed

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
                    balance_after=balance,
                    reason=command.reason,
                    reference=command.reference,
                    idempotency_key=command.idempotency_key,
                    request_fingerprint=fingerprint,
                )
                .returning(StockMovement.id)
            )
    except IntegrityError as error:
        if (
            error.orig.diag.constraint_name
            != "uq_stock_movements_organization_idempotency_key"
        ):
            raise
        with engine.connect() as connection:
            replayed = _replayed_result(connection, command, fingerprint)
            if replayed is None:
                raise
            return replayed

    return MovementResult(movement_id=movement_id, balance=balance, replayed=False)
