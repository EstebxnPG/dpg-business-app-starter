from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, and_, exists, or_, select

from app.core.authorization import (
    CurrentMembership,
    OrganizationNotFoundError,
    Permission,
    require_permission,
)
from app.modules.inventory.models import StockBalance, StockMovement
from app.modules.inventory.service import (
    MovementResult,
    MovementType,
    RecordMovementCommand,
    record_stock_movement,
)
from app.modules.products.models import Product
from app.modules.warehouses.models import Warehouse

MOVEMENT_PERMISSIONS = {
    MovementType.RECEIPT: Permission.INVENTORY_RECEIVE,
    MovementType.ISSUE: Permission.INVENTORY_ISSUE,
}


@dataclass(frozen=True)
class RecordManualMovementCommand:
    organization_id: UUID
    product_id: UUID
    warehouse_id: UUID
    movement_type: MovementType
    quantity: Decimal
    reason: str
    idempotency_key: str
    reference: str | None = None


class InventoryContextNotFoundError(Exception):
    pass


class InvalidMovementCursorError(Exception):
    pass


@dataclass(frozen=True)
class StockPosition:
    product_id: UUID
    warehouse_id: UUID
    quantity: Decimal


@dataclass(frozen=True)
class MovementHistoryItem:
    id: UUID
    performed_by_id: UUID
    movement_type: str
    quantity: Decimal
    balance_after: Decimal
    reason: str
    reference: str | None
    created_at: datetime


@dataclass(frozen=True)
class MovementHistoryPage:
    items: list[MovementHistoryItem]
    next_cursor: UUID | None


def _require_inventory_context(
    connection,
    organization_id: UUID,
    product_id: UUID,
    warehouse_id: UUID,
) -> None:
    product_exists = connection.scalar(
        select(
            exists().where(
                Product.organization_id == organization_id,
                Product.id == product_id,
            )
        )
    )
    warehouse_exists = connection.scalar(
        select(
            exists().where(
                Warehouse.organization_id == organization_id,
                Warehouse.id == warehouse_id,
            )
        )
    )
    if not product_exists or not warehouse_exists:
        raise InventoryContextNotFoundError


def record_manual_stock_movement(
    engine: Engine,
    membership: CurrentMembership,
    command: RecordManualMovementCommand,
) -> MovementResult:
    if membership.organization_id != command.organization_id:
        raise OrganizationNotFoundError

    require_permission(membership, MOVEMENT_PERMISSIONS[command.movement_type])

    return record_stock_movement(
        engine,
        RecordMovementCommand(
            organization_id=command.organization_id,
            product_id=command.product_id,
            warehouse_id=command.warehouse_id,
            performed_by_id=membership.user_id,
            movement_type=command.movement_type,
            quantity=command.quantity,
            reason=command.reason,
            reference=command.reference,
            idempotency_key=command.idempotency_key,
        ),
    )


def get_stock_position(
    engine: Engine,
    membership: CurrentMembership,
    product_id: UUID,
    warehouse_id: UUID,
) -> StockPosition:
    require_permission(membership, Permission.INVENTORY_READ)

    with engine.connect() as connection:
        _require_inventory_context(
            connection,
            membership.organization_id,
            product_id,
            warehouse_id,
        )
        quantity = connection.scalar(
            select(StockBalance.quantity).where(
                StockBalance.organization_id == membership.organization_id,
                StockBalance.product_id == product_id,
                StockBalance.warehouse_id == warehouse_id,
            )
        )

    return StockPosition(
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity=quantity if quantity is not None else Decimal("0"),
    )


def list_stock_movements(
    engine: Engine,
    membership: CurrentMembership,
    product_id: UUID,
    warehouse_id: UUID,
    limit: int,
    cursor: UUID | None,
) -> MovementHistoryPage:
    require_permission(membership, Permission.INVENTORY_READ)
    filters = [
        StockMovement.organization_id == membership.organization_id,
        StockMovement.product_id == product_id,
        StockMovement.warehouse_id == warehouse_id,
    ]

    with engine.connect() as connection:
        _require_inventory_context(
            connection,
            membership.organization_id,
            product_id,
            warehouse_id,
        )

        if cursor is not None:
            cursor_row = connection.execute(
                select(StockMovement.created_at, StockMovement.id).where(
                    *filters,
                    StockMovement.id == cursor,
                )
            ).one_or_none()
            if cursor_row is None:
                raise InvalidMovementCursorError
            filters.append(
                or_(
                    StockMovement.created_at < cursor_row.created_at,
                    and_(
                        StockMovement.created_at == cursor_row.created_at,
                        StockMovement.id < cursor_row.id,
                    ),
                )
            )

        rows = connection.execute(
            select(
                StockMovement.id,
                StockMovement.performed_by_id,
                StockMovement.movement_type,
                StockMovement.quantity,
                StockMovement.balance_after,
                StockMovement.reason,
                StockMovement.reference,
                StockMovement.created_at,
            )
            .where(*filters)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(limit + 1)
        ).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return MovementHistoryPage(
        items=[MovementHistoryItem(**row._mapping) for row in page_rows],
        next_cursor=page_rows[-1].id if has_more else None,
    )
