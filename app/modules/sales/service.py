import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

from app.core.security import password_hasher
from app.modules.inventory.models import StockBalance, StockMovement
from app.modules.inventory.service import MovementType
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.sales.models import Sale, SaleLine
from app.modules.warehouses.models import Warehouse

PIN_FAILURE_LIMIT = 5
PIN_LOCK_MINUTES = 15


class SaleContextNotFoundError(Exception):
    pass


class InactiveSaleContextError(Exception):
    pass


class SalePriceBelowCostError(Exception):
    pass


class SalePriceAboveListError(Exception):
    pass


class DiscountReasonRequiredError(Exception):
    pass


class DiscountApprovalRequiredError(Exception):
    pass


class InvalidApprovalPinError(Exception):
    pass


class ApprovalPinLockedError(Exception):
    pass


class SaleIdempotencyConflictError(Exception):
    pass


class SaleInsufficientStockError(Exception):
    def __init__(self, product_id: UUID) -> None:
        self.product_id = product_id


@dataclass(frozen=True)
class SaleLineCommand:
    product_id: UUID
    quantity: Decimal
    unit_price: Decimal | None


@dataclass(frozen=True)
class SaleApproval:
    approver_user_id: UUID
    pin: str


@dataclass(frozen=True)
class CreateSaleCommand:
    organization_id: UUID
    warehouse_id: UUID
    sold_by_id: UUID
    seller_role: str
    lines: tuple[SaleLineCommand, ...]
    discount_reason: str | None
    approval: SaleApproval | None
    idempotency_key: str


@dataclass(frozen=True)
class SaleResult:
    sale_id: UUID
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    cost_total: Decimal
    approved_by_id: UUID | None
    replayed: bool


def _fingerprint(command: CreateSaleCommand) -> str:
    payload = {
        "organization_id": str(command.organization_id),
        "warehouse_id": str(command.warehouse_id),
        "sold_by_id": str(command.sold_by_id),
        "lines": sorted(
            [
                {
                    "product_id": str(line.product_id),
                    "quantity": format(line.quantity.normalize(), "f"),
                    "unit_price": (
                        format(line.unit_price.normalize(), "f")
                        if line.unit_price is not None
                        else None
                    ),
                }
                for line in command.lines
            ],
            key=lambda item: item["product_id"],
        ),
        "discount_reason": command.discount_reason,
        "approver_user_id": (
            str(command.approval.approver_user_id) if command.approval else None
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _replayed_sale(connection, command, fingerprint) -> SaleResult | None:
    row = connection.execute(
        select(
            Sale.id,
            Sale.subtotal,
            Sale.discount_total,
            Sale.total,
            Sale.cost_total,
            Sale.approved_by_id,
            Sale.request_fingerprint,
        ).where(
            Sale.organization_id == command.organization_id,
            Sale.idempotency_key == command.idempotency_key,
        )
    ).one_or_none()
    if row is None:
        return None
    if row.request_fingerprint != fingerprint:
        raise SaleIdempotencyConflictError
    return SaleResult(
        sale_id=row.id,
        subtotal=row.subtotal,
        discount_total=row.discount_total,
        total=row.total,
        cost_total=row.cost_total,
        approved_by_id=row.approved_by_id,
        replayed=True,
    )


def create_sale(engine: Engine, command: CreateSaleCommand) -> SaleResult:
    if not command.lines or len({line.product_id for line in command.lines}) != len(
        command.lines
    ):
        raise ValueError("Sale lines must contain unique products")
    fingerprint = _fingerprint(command)
    pin_error = None
    result = None

    try:
        with engine.begin() as connection:
            replayed = _replayed_sale(connection, command, fingerprint)
            if replayed is not None:
                return replayed

            policy = connection.scalar(
                select(Organization.salesperson_max_discount_rate)
                .where(
                    Organization.id == command.organization_id,
                    Organization.active.is_(True),
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
            product_ids = sorted((line.product_id for line in command.lines), key=str)
            products = connection.execute(
                select(
                    Product.id,
                    Product.sku,
                    Product.name,
                    Product.cost,
                    Product.sale_price,
                    Product.active,
                )
                .where(
                    Product.organization_id == command.organization_id,
                    Product.id.in_(product_ids),
                )
                .order_by(Product.id)
                .with_for_update(read=True)
            ).all()
            if (
                policy is None
                or warehouse_active is None
                or len(products) != len(product_ids)
            ):
                raise SaleContextNotFoundError
            if not warehouse_active or not all(product.active for product in products):
                raise InactiveSaleContextError

            products_by_id = {product.id: product for product in products}
            priced_lines = []
            requires_approval = False
            has_discount = False
            for line in command.lines:
                product = products_by_id[line.product_id]
                unit_price = (
                    line.unit_price
                    if line.unit_price is not None
                    else product.sale_price
                )
                if unit_price < product.cost:
                    raise SalePriceBelowCostError
                if unit_price > product.sale_price:
                    raise SalePriceAboveListError
                discount_rate = (
                    (product.sale_price - unit_price) / product.sale_price
                    if product.sale_price > 0
                    else Decimal("0")
                )
                has_discount = has_discount or unit_price < product.sale_price
                requires_approval = requires_approval or discount_rate > policy
                priced_lines.append((line, product, unit_price))

            if has_discount and not command.discount_reason:
                raise DiscountReasonRequiredError

            approved_by_id = None
            if requires_approval:
                if command.seller_role == "admin":
                    approved_by_id = command.sold_by_id
                elif command.approval is None:
                    raise DiscountApprovalRequiredError
                else:
                    approver = connection.execute(
                        select(
                            Membership.role,
                            Membership.approval_pin_hash,
                            Membership.approval_pin_failures,
                            Membership.approval_pin_locked_until,
                        )
                        .where(
                            Membership.organization_id == command.organization_id,
                            Membership.user_id == command.approval.approver_user_id,
                        )
                        .with_for_update()
                    ).one_or_none()
                    now = datetime.now(UTC)
                    if (
                        approver is not None
                        and approver.approval_pin_locked_until is not None
                        and approver.approval_pin_locked_until > now
                    ):
                        pin_error = ApprovalPinLockedError()
                    elif (
                        approver is None
                        or approver.role != "admin"
                        or approver.approval_pin_hash is None
                        or not password_hasher.verify(
                            command.approval.pin, approver.approval_pin_hash
                        )
                    ):
                        pin_error = InvalidApprovalPinError()
                        if approver is not None and approver.role == "admin":
                            failures = approver.approval_pin_failures + 1
                            connection.execute(
                                update(Membership)
                                .where(
                                    Membership.organization_id
                                    == command.organization_id,
                                    Membership.user_id
                                    == command.approval.approver_user_id,
                                )
                                .values(
                                    approval_pin_failures=failures,
                                    approval_pin_locked_until=(
                                        now + timedelta(minutes=PIN_LOCK_MINUTES)
                                        if failures >= PIN_FAILURE_LIMIT
                                        else None
                                    ),
                                )
                            )
                    else:
                        approved_by_id = command.approval.approver_user_id
                        connection.execute(
                            update(Membership)
                            .where(
                                Membership.organization_id == command.organization_id,
                                Membership.user_id == approved_by_id,
                            )
                            .values(
                                approval_pin_failures=0,
                                approval_pin_locked_until=None,
                            )
                        )

            if pin_error is None:
                connection.execute(
                    postgresql_insert(StockBalance)
                    .values(
                        [
                            {
                                "organization_id": command.organization_id,
                                "product_id": product_id,
                                "warehouse_id": command.warehouse_id,
                                "quantity": Decimal("0"),
                            }
                            for product_id in product_ids
                        ]
                    )
                    .on_conflict_do_nothing()
                )
                connection.execute(
                    select(StockBalance.product_id)
                    .where(
                        StockBalance.organization_id == command.organization_id,
                        StockBalance.warehouse_id == command.warehouse_id,
                        StockBalance.product_id.in_(product_ids),
                    )
                    .order_by(StockBalance.product_id)
                    .with_for_update()
                ).all()

                subtotal = sum(
                    (
                        product.sale_price * line.quantity
                        for line, product, _ in priced_lines
                    ),
                    Decimal("0"),
                )
                total = sum(
                    (
                        unit_price * line.quantity
                        for line, _, unit_price in priced_lines
                    ),
                    Decimal("0"),
                )
                cost_total = sum(
                    (product.cost * line.quantity for line, product, _ in priced_lines),
                    Decimal("0"),
                )
                sale_id = connection.scalar(
                    insert(Sale)
                    .values(
                        organization_id=command.organization_id,
                        warehouse_id=command.warehouse_id,
                        sold_by_id=command.sold_by_id,
                        approved_by_id=approved_by_id,
                        subtotal=subtotal,
                        discount_total=subtotal - total,
                        total=total,
                        cost_total=cost_total,
                        approval_reason=command.discount_reason,
                        idempotency_key=command.idempotency_key,
                        request_fingerprint=fingerprint,
                    )
                    .returning(Sale.id)
                )
                movement_prefix = hashlib.sha256(f"sale:{sale_id}".encode()).hexdigest()
                for line, product, unit_price in priced_lines:
                    balance = connection.scalar(
                        update(StockBalance)
                        .where(
                            StockBalance.organization_id == command.organization_id,
                            StockBalance.product_id == line.product_id,
                            StockBalance.warehouse_id == command.warehouse_id,
                            StockBalance.quantity >= line.quantity,
                        )
                        .values(quantity=StockBalance.quantity - line.quantity)
                        .returning(StockBalance.quantity)
                    )
                    if balance is None:
                        raise SaleInsufficientStockError(line.product_id)
                    connection.execute(
                        insert(SaleLine).values(
                            sale_id=sale_id,
                            product_id=line.product_id,
                            organization_id=command.organization_id,
                            quantity=line.quantity,
                            product_sku=product.sku,
                            product_name=product.name,
                            list_unit_price=product.sale_price,
                            unit_price=unit_price,
                            unit_cost=product.cost,
                            line_total=unit_price * line.quantity,
                        )
                    )
                    connection.execute(
                        insert(StockMovement).values(
                            organization_id=command.organization_id,
                            product_id=line.product_id,
                            warehouse_id=command.warehouse_id,
                            performed_by_id=command.sold_by_id,
                            sale_id=sale_id,
                            movement_type=MovementType.ISSUE.value,
                            quantity=line.quantity,
                            balance_after=balance,
                            reason="Sale",
                            reference=str(sale_id),
                            idempotency_key=f"{movement_prefix}:{line.product_id}",
                            request_fingerprint=fingerprint,
                        )
                    )
                result = SaleResult(
                    sale_id=sale_id,
                    subtotal=subtotal,
                    discount_total=subtotal - total,
                    total=total,
                    cost_total=cost_total,
                    approved_by_id=approved_by_id,
                    replayed=False,
                )
    except IntegrityError as error:
        if error.orig.diag.constraint_name != "uq_sales_organization_idempotency_key":
            raise
        with engine.connect() as connection:
            replayed = _replayed_sale(connection, command, fingerprint)
            if replayed is None:
                raise
            return replayed

    if pin_error is not None:
        raise pin_error
    if result is None:
        raise RuntimeError("Sale did not produce a result")
    return result
