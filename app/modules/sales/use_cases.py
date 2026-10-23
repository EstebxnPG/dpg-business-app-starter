from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, select, update

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.core.security import hash_password
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.sales.service import (
    CreateSaleCommand,
    SaleApproval,
    SaleLineCommand,
    SaleResult,
    create_sale,
)


@dataclass(frozen=True)
class SubmitSaleLine:
    product_id: UUID
    quantity: Decimal
    unit_price: Decimal | None


@dataclass(frozen=True)
class SubmitSaleApproval:
    approver_user_id: UUID
    pin: str


@dataclass(frozen=True)
class SubmitSaleCommand:
    organization_id: UUID
    warehouse_id: UUID
    lines: tuple[SubmitSaleLine, ...]
    discount_reason: str | None
    approval: SubmitSaleApproval | None
    idempotency_key: str


def submit_sale(
    engine: Engine,
    membership: CurrentMembership,
    command: SubmitSaleCommand,
) -> SaleResult:
    require_permission(membership, Permission.SALES_CREATE)
    return create_sale(
        engine,
        CreateSaleCommand(
            organization_id=membership.organization_id,
            warehouse_id=command.warehouse_id,
            sold_by_id=membership.user_id,
            seller_role=membership.role,
            lines=tuple(
                SaleLineCommand(line.product_id, line.quantity, line.unit_price)
                for line in command.lines
            ),
            discount_reason=command.discount_reason,
            approval=(
                SaleApproval(command.approval.approver_user_id, command.approval.pin)
                if command.approval
                else None
            ),
            idempotency_key=command.idempotency_key,
        ),
    )


def update_sales_policy(
    engine: Engine,
    membership: CurrentMembership,
    max_discount_rate: Decimal,
) -> Decimal:
    require_permission(membership, Permission.CATALOG_MANAGE)
    with engine.begin() as connection:
        return connection.scalar(
            update(Organization)
            .where(Organization.id == membership.organization_id)
            .values(salesperson_max_discount_rate=max_discount_rate)
            .returning(Organization.salesperson_max_discount_rate)
        )


def set_approval_pin(
    engine: Engine,
    membership: CurrentMembership,
    pin: str,
) -> None:
    if membership.role != "admin":
        require_permission(membership, Permission.CATALOG_MANAGE)
    pin_hash = hash_password(pin)
    with engine.begin() as connection:
        connection.execute(
            update(Membership)
            .where(
                Membership.organization_id == membership.organization_id,
                Membership.user_id == membership.user_id,
                Membership.role == "admin",
            )
            .values(
                approval_pin_hash=pin_hash,
                approval_pin_failures=0,
                approval_pin_locked_until=None,
            )
        )


def get_sales_policy(engine: Engine, membership: CurrentMembership) -> Decimal:
    require_permission(membership, Permission.SALES_CREATE)
    with engine.connect() as connection:
        return connection.scalar(
            select(Organization.salesperson_max_discount_rate).where(
                Organization.id == membership.organization_id
            )
        )
