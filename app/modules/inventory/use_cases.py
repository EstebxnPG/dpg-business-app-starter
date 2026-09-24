from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine

from app.core.authorization import (
    CurrentMembership,
    OrganizationNotFoundError,
    Permission,
    require_permission,
)
from app.modules.inventory.service import (
    MovementResult,
    MovementType,
    RecordMovementCommand,
    record_stock_movement,
)

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
