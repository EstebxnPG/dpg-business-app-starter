import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

from app.modules.inventory.models import StockBalance, StockMovement, StockTransfer
from app.modules.products.models import Product
from app.modules.warehouses.models import Warehouse


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"


class StockCondition(StrEnum):
    AVAILABLE = "AVAILABLE"
    DAMAGED = "DAMAGED"


class InvalidMovementQuantityError(ValueError):
    pass


class InsufficientStockError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
    pass


class InventoryContextNotFoundError(ValueError):
    pass


class InactiveInventoryContextError(ValueError):
    pass


class SameWarehouseTransferError(ValueError):
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


@dataclass(frozen=True)
class TransferStockCommand:
    organization_id: UUID
    product_id: UUID
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    performed_by_id: UUID
    quantity: Decimal
    reason: str
    idempotency_key: str
    reference: str | None = None


@dataclass(frozen=True)
class TransferResult:
    transfer_id: UUID
    source_balance: Decimal
    destination_balance: Decimal
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

            product_active = connection.scalar(
                select(Product.active)
                .where(
                    Product.organization_id == command.organization_id,
                    Product.id == command.product_id,
                )
                .with_for_update(read=True)
            )
            warehouse_active = connection.scalar(
                select(Warehouse.active)
                .where(
                    Warehouse.organization_id == command.organization_id,
                    Warehouse.id == command.warehouse_id,
                )
                .with_for_update(read=True)
            )
            if product_active is None or warehouse_active is None:
                raise InventoryContextNotFoundError
            if not product_active or not warehouse_active:
                raise InactiveInventoryContextError

            if command.movement_type is MovementType.RECEIPT:
                balance = connection.scalar(
                    postgresql_insert(StockBalance)
                    .values(
                        organization_id=command.organization_id,
                        product_id=command.product_id,
                        warehouse_id=command.warehouse_id,
                        condition=StockCondition.AVAILABLE.value,
                        quantity=command.quantity,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            StockBalance.organization_id,
                            StockBalance.product_id,
                            StockBalance.warehouse_id,
                            StockBalance.condition,
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
                        StockBalance.condition == StockCondition.AVAILABLE.value,
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
                    stock_condition=StockCondition.AVAILABLE.value,
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


def _transfer_fingerprint(command: TransferStockCommand) -> str:
    payload = {
        "organization_id": str(command.organization_id),
        "product_id": str(command.product_id),
        "source_warehouse_id": str(command.source_warehouse_id),
        "destination_warehouse_id": str(command.destination_warehouse_id),
        "performed_by_id": str(command.performed_by_id),
        "quantity": format(command.quantity.normalize(), "f"),
        "reason": command.reason,
        "reference": command.reference,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _replayed_transfer(connection, command, fingerprint) -> TransferResult | None:
    existing = connection.execute(
        select(
            StockTransfer.id,
            StockTransfer.source_balance_after,
            StockTransfer.destination_balance_after,
            StockTransfer.request_fingerprint,
        ).where(
            StockTransfer.organization_id == command.organization_id,
            StockTransfer.idempotency_key == command.idempotency_key,
        )
    ).one_or_none()
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflictError(
            "Idempotency key was already used with different transfer data"
        )
    return TransferResult(
        transfer_id=existing.id,
        source_balance=existing.source_balance_after,
        destination_balance=existing.destination_balance_after,
        replayed=True,
    )


def transfer_stock(engine: Engine, command: TransferStockCommand) -> TransferResult:
    if command.quantity <= 0:
        raise InvalidMovementQuantityError("Transfer quantity must be positive")
    if command.source_warehouse_id == command.destination_warehouse_id:
        raise SameWarehouseTransferError
    if not command.idempotency_key.strip():
        raise ValueError("Idempotency key must not be empty")

    fingerprint = _transfer_fingerprint(command)
    movement_key_prefix = hashlib.sha256(
        f"transfer:{command.organization_id}:{command.idempotency_key}".encode()
    ).hexdigest()

    try:
        with engine.begin() as connection:
            replayed = _replayed_transfer(connection, command, fingerprint)
            if replayed is not None:
                return replayed

            product_active = connection.scalar(
                select(Product.active)
                .where(
                    Product.organization_id == command.organization_id,
                    Product.id == command.product_id,
                )
                .with_for_update(read=True)
            )
            warehouse_rows = connection.execute(
                select(Warehouse.id, Warehouse.active)
                .where(
                    Warehouse.organization_id == command.organization_id,
                    Warehouse.id.in_(
                        [command.source_warehouse_id, command.destination_warehouse_id]
                    ),
                )
                .order_by(Warehouse.id)
                .with_for_update(read=True)
            ).all()
            if product_active is None or len(warehouse_rows) != 2:
                raise InventoryContextNotFoundError
            if not product_active or not all(row.active for row in warehouse_rows):
                raise InactiveInventoryContextError

            connection.execute(
                postgresql_insert(StockBalance)
                .values(
                    [
                        {
                            "organization_id": command.organization_id,
                            "product_id": command.product_id,
                            "warehouse_id": warehouse_id,
                            "condition": StockCondition.AVAILABLE.value,
                            "quantity": Decimal("0"),
                        }
                        for warehouse_id in (
                            command.source_warehouse_id,
                            command.destination_warehouse_id,
                        )
                    ]
                )
                .on_conflict_do_nothing()
            )
            connection.execute(
                select(StockBalance.warehouse_id)
                .where(
                    StockBalance.organization_id == command.organization_id,
                    StockBalance.product_id == command.product_id,
                    StockBalance.warehouse_id.in_(
                        [command.source_warehouse_id, command.destination_warehouse_id]
                    ),
                    StockBalance.condition == StockCondition.AVAILABLE.value,
                )
                .order_by(StockBalance.warehouse_id)
                .with_for_update()
            ).all()

            source_balance = connection.scalar(
                update(StockBalance)
                .where(
                    StockBalance.organization_id == command.organization_id,
                    StockBalance.product_id == command.product_id,
                    StockBalance.warehouse_id == command.source_warehouse_id,
                    StockBalance.condition == StockCondition.AVAILABLE.value,
                    StockBalance.quantity >= command.quantity,
                )
                .values(quantity=StockBalance.quantity - command.quantity)
                .returning(StockBalance.quantity)
            )
            if source_balance is None:
                raise InsufficientStockError("Insufficient stock for this transfer")

            destination_balance = connection.scalar(
                update(StockBalance)
                .where(
                    StockBalance.organization_id == command.organization_id,
                    StockBalance.product_id == command.product_id,
                    StockBalance.warehouse_id == command.destination_warehouse_id,
                    StockBalance.condition == StockCondition.AVAILABLE.value,
                )
                .values(quantity=StockBalance.quantity + command.quantity)
                .returning(StockBalance.quantity)
            )
            transfer_id = connection.scalar(
                insert(StockTransfer)
                .values(
                    organization_id=command.organization_id,
                    product_id=command.product_id,
                    source_warehouse_id=command.source_warehouse_id,
                    destination_warehouse_id=command.destination_warehouse_id,
                    performed_by_id=command.performed_by_id,
                    quantity=command.quantity,
                    source_balance_after=source_balance,
                    destination_balance_after=destination_balance,
                    reason=command.reason,
                    reference=command.reference,
                    idempotency_key=command.idempotency_key,
                    request_fingerprint=fingerprint,
                )
                .returning(StockTransfer.id)
            )
            connection.execute(
                insert(StockMovement),
                [
                    {
                        "organization_id": command.organization_id,
                        "product_id": command.product_id,
                        "warehouse_id": command.source_warehouse_id,
                        "performed_by_id": command.performed_by_id,
                        "transfer_id": transfer_id,
                        "stock_condition": StockCondition.AVAILABLE.value,
                        "movement_type": MovementType.ISSUE.value,
                        "quantity": command.quantity,
                        "balance_after": source_balance,
                        "reason": command.reason,
                        "reference": command.reference,
                        "idempotency_key": f"{movement_key_prefix}:out",
                        "request_fingerprint": fingerprint,
                    },
                    {
                        "organization_id": command.organization_id,
                        "product_id": command.product_id,
                        "warehouse_id": command.destination_warehouse_id,
                        "performed_by_id": command.performed_by_id,
                        "transfer_id": transfer_id,
                        "stock_condition": StockCondition.AVAILABLE.value,
                        "movement_type": MovementType.RECEIPT.value,
                        "quantity": command.quantity,
                        "balance_after": destination_balance,
                        "reason": command.reason,
                        "reference": command.reference,
                        "idempotency_key": f"{movement_key_prefix}:in",
                        "request_fingerprint": fingerprint,
                    },
                ],
            )
    except IntegrityError as error:
        if (
            error.orig.diag.constraint_name
            != "uq_stock_transfers_organization_idempotency_key"
        ):
            raise
        with engine.connect() as connection:
            replayed = _replayed_transfer(connection, command, fingerprint)
            if replayed is None:
                raise
            return replayed

    return TransferResult(
        transfer_id=transfer_id,
        source_balance=source_balance,
        destination_balance=destination_balance,
        replayed=False,
    )
