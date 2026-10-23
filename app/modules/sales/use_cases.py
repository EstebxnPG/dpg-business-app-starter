from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, and_, or_, select, update

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.core.security import hash_password
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.sales.models import Sale, SaleLine
from app.modules.sales.service import (
    CreateSaleCommand,
    SaleApproval,
    SaleLineCommand,
    SaleResult,
    create_sale,
)
from app.modules.warehouses.models import Warehouse


class SaleNotFoundError(Exception):
    pass


class InvalidSaleCursorError(Exception):
    pass


@dataclass(frozen=True)
class SaleSummary:
    id: UUID
    warehouse_id: UUID
    sold_by_id: UUID
    approved_by_id: UUID | None
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    cost_total: Decimal
    created_at: datetime


@dataclass(frozen=True)
class SalePage:
    items: list[SaleSummary]
    next_cursor: UUID | None


@dataclass(frozen=True)
class ReceiptLine:
    product_id: UUID
    sku: str
    name: str
    quantity: Decimal
    list_unit_price: Decimal
    unit_price: Decimal
    unit_cost: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class SaleReceipt:
    sale_id: UUID
    organization_name: str
    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    sold_by_id: UUID
    approved_by_id: UUID | None
    approval_reason: str | None
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    cost_total: Decimal
    created_at: datetime
    lines: list[ReceiptLine]


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


def list_sales(
    engine: Engine,
    membership: CurrentMembership,
    limit: int,
    cursor: UUID | None,
) -> SalePage:
    require_permission(membership, Permission.SALES_READ)
    filters = [Sale.organization_id == membership.organization_id]
    with engine.connect() as connection:
        if cursor is not None:
            cursor_row = connection.execute(
                select(Sale.created_at, Sale.id).where(*filters, Sale.id == cursor)
            ).one_or_none()
            if cursor_row is None:
                raise InvalidSaleCursorError
            filters.append(
                or_(
                    Sale.created_at < cursor_row.created_at,
                    and_(
                        Sale.created_at == cursor_row.created_at,
                        Sale.id < cursor_row.id,
                    ),
                )
            )

        rows = connection.execute(
            select(
                Sale.id,
                Sale.warehouse_id,
                Sale.sold_by_id,
                Sale.approved_by_id,
                Sale.subtotal,
                Sale.discount_total,
                Sale.total,
                Sale.cost_total,
                Sale.created_at,
            )
            .where(*filters)
            .order_by(Sale.created_at.desc(), Sale.id.desc())
            .limit(limit + 1)
        ).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return SalePage(
        items=[SaleSummary(**row._mapping) for row in page_rows],
        next_cursor=page_rows[-1].id if has_more else None,
    )


def get_sale_receipt(
    engine: Engine,
    membership: CurrentMembership,
    sale_id: UUID,
) -> SaleReceipt:
    require_permission(membership, Permission.SALES_READ)
    with engine.connect() as connection:
        sale = connection.execute(
            select(
                Sale.id.label("sale_id"),
                Organization.name.label("organization_name"),
                Sale.warehouse_id,
                Warehouse.code.label("warehouse_code"),
                Warehouse.name.label("warehouse_name"),
                Sale.sold_by_id,
                Sale.approved_by_id,
                Sale.approval_reason,
                Sale.subtotal,
                Sale.discount_total,
                Sale.total,
                Sale.cost_total,
                Sale.created_at,
            )
            .join(Organization, Organization.id == Sale.organization_id)
            .join(
                Warehouse,
                and_(
                    Warehouse.organization_id == Sale.organization_id,
                    Warehouse.id == Sale.warehouse_id,
                ),
            )
            .where(
                Sale.organization_id == membership.organization_id,
                Sale.id == sale_id,
            )
        ).one_or_none()
        if sale is None:
            raise SaleNotFoundError

        lines = connection.execute(
            select(
                SaleLine.product_id,
                SaleLine.product_sku.label("sku"),
                SaleLine.product_name.label("name"),
                SaleLine.quantity,
                SaleLine.list_unit_price,
                SaleLine.unit_price,
                SaleLine.unit_cost,
                SaleLine.line_total,
            )
            .where(
                SaleLine.organization_id == membership.organization_id,
                SaleLine.sale_id == sale_id,
            )
            .order_by(SaleLine.product_sku, SaleLine.product_id)
        ).all()

    return SaleReceipt(
        **sale._mapping,
        lines=[ReceiptLine(**line._mapping) for line in lines],
    )
