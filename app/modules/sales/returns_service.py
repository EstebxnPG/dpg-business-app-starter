import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Engine, func, insert, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

from app.modules.inventory.models import StockBalance, StockMovement
from app.modules.inventory.service import MovementType, StockCondition
from app.modules.sales.models import Sale, SaleLine, SaleReturn, SaleReturnLine


class ReturnKind(StrEnum):
    RETURN = "RETURN"
    VOID = "VOID"


class ReturnDisposition(StrEnum):
    RESTOCK = "RESTOCK"
    DAMAGED = "DAMAGED"


class RefundResolution(StrEnum):
    REFUNDED_NOW = "REFUNDED_NOW"
    NO_REFUND = "NO_REFUND"


class ReturnSaleNotFoundError(Exception):
    pass


class ReturnQuantityExceededError(Exception):
    def __init__(self, product_id: UUID) -> None:
        self.product_id = product_id


class SaleAlreadyAdjustedError(Exception):
    pass


class ReturnIdempotencyConflictError(Exception):
    pass


@dataclass(frozen=True)
class ReturnLineCommand:
    product_id: UUID
    quantity: Decimal
    disposition: ReturnDisposition


@dataclass(frozen=True)
class ProcessSaleReturnCommand:
    organization_id: UUID
    sale_id: UUID
    processed_by_id: UUID
    kind: ReturnKind
    refund_resolution: RefundResolution
    reason: str
    idempotency_key: str
    lines: tuple[ReturnLineCommand, ...] = ()


@dataclass(frozen=True)
class SaleReturnResult:
    sale_return_id: UUID
    sale_id: UUID
    kind: ReturnKind
    refund_resolution: RefundResolution
    return_value: Decimal
    refunded_amount: Decimal
    replayed: bool


def _fingerprint(command: ProcessSaleReturnCommand) -> str:
    payload = {
        "organization_id": str(command.organization_id),
        "sale_id": str(command.sale_id),
        "processed_by_id": str(command.processed_by_id),
        "kind": command.kind.value,
        "refund_resolution": command.refund_resolution.value,
        "reason": command.reason,
        "lines": sorted(
            [
                {
                    "product_id": str(line.product_id),
                    "quantity": format(line.quantity.normalize(), "f"),
                    "disposition": line.disposition.value,
                }
                for line in command.lines
            ],
            key=lambda item: item["product_id"],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _replayed_return(connection, command, fingerprint) -> SaleReturnResult | None:
    row = connection.execute(
        select(
            SaleReturn.id,
            SaleReturn.sale_id,
            SaleReturn.kind,
            SaleReturn.refund_resolution,
            SaleReturn.return_value,
            SaleReturn.refunded_amount,
            SaleReturn.request_fingerprint,
        ).where(
            SaleReturn.organization_id == command.organization_id,
            SaleReturn.idempotency_key == command.idempotency_key,
        )
    ).one_or_none()
    if row is None:
        return None
    if row.request_fingerprint != fingerprint:
        raise ReturnIdempotencyConflictError
    return SaleReturnResult(
        sale_return_id=row.id,
        sale_id=row.sale_id,
        kind=ReturnKind(row.kind),
        refund_resolution=RefundResolution(row.refund_resolution),
        return_value=row.return_value,
        refunded_amount=row.refunded_amount,
        replayed=True,
    )


def process_sale_return(
    engine: Engine, command: ProcessSaleReturnCommand
) -> SaleReturnResult:
    if not command.reason.strip():
        raise ValueError("Return reason must not be blank")
    if command.kind is ReturnKind.RETURN:
        if not command.lines or len({line.product_id for line in command.lines}) != len(
            command.lines
        ):
            raise ValueError("Return lines must contain unique products")
        if any(line.quantity <= 0 for line in command.lines):
            raise ValueError("Return quantities must be positive")
    fingerprint = _fingerprint(command)

    try:
        with engine.begin() as connection:
            replayed = _replayed_return(connection, command, fingerprint)
            if replayed is not None:
                return replayed

            sale = connection.execute(
                select(Sale.id, Sale.warehouse_id)
                .where(
                    Sale.organization_id == command.organization_id,
                    Sale.id == command.sale_id,
                )
                .with_for_update()
            ).one_or_none()
            if sale is None:
                raise ReturnSaleNotFoundError

            replayed = _replayed_return(connection, command, fingerprint)
            if replayed is not None:
                return replayed

            sale_lines = connection.execute(
                select(
                    SaleLine.product_id,
                    SaleLine.quantity,
                    SaleLine.unit_price,
                )
                .where(
                    SaleLine.organization_id == command.organization_id,
                    SaleLine.sale_id == command.sale_id,
                )
                .order_by(SaleLine.product_id)
            ).all()
            lines_by_product = {line.product_id: line for line in sale_lines}
            previous_returns = connection.execute(
                select(
                    SaleReturnLine.product_id,
                    func.sum(SaleReturnLine.quantity).label("quantity"),
                )
                .join(
                    SaleReturn,
                    (SaleReturn.organization_id == SaleReturnLine.organization_id)
                    & (SaleReturn.id == SaleReturnLine.sale_return_id),
                )
                .where(
                    SaleReturn.organization_id == command.organization_id,
                    SaleReturn.sale_id == command.sale_id,
                )
                .group_by(SaleReturnLine.product_id)
            ).all()
            returned_by_product = {
                row.product_id: row.quantity for row in previous_returns
            }
            has_previous_adjustment = connection.scalar(
                select(
                    select(SaleReturn.id)
                    .where(
                        SaleReturn.organization_id == command.organization_id,
                        SaleReturn.sale_id == command.sale_id,
                    )
                    .exists()
                )
            )

            if command.kind is ReturnKind.VOID:
                if has_previous_adjustment:
                    raise SaleAlreadyAdjustedError
                effective_lines = tuple(
                    ReturnLineCommand(
                        product_id=line.product_id,
                        quantity=line.quantity,
                        disposition=ReturnDisposition.RESTOCK,
                    )
                    for line in sale_lines
                )
            else:
                if connection.scalar(
                    select(
                        select(SaleReturn.id)
                        .where(
                            SaleReturn.organization_id == command.organization_id,
                            SaleReturn.sale_id == command.sale_id,
                            SaleReturn.kind == ReturnKind.VOID.value,
                        )
                        .exists()
                    )
                ):
                    raise SaleAlreadyAdjustedError
                effective_lines = command.lines

            return_value = Decimal("0")
            for line in effective_lines:
                sold_line = lines_by_product.get(line.product_id)
                already_returned = returned_by_product.get(
                    line.product_id, Decimal("0")
                )
                if (
                    sold_line is None
                    or line.quantity > sold_line.quantity - already_returned
                ):
                    raise ReturnQuantityExceededError(line.product_id)
                return_value += sold_line.unit_price * line.quantity

            refunded_amount = (
                return_value
                if command.refund_resolution is RefundResolution.REFUNDED_NOW
                else Decimal("0")
            )
            sale_return_id = connection.scalar(
                insert(SaleReturn)
                .values(
                    organization_id=command.organization_id,
                    sale_id=command.sale_id,
                    processed_by_id=command.processed_by_id,
                    kind=command.kind.value,
                    refund_resolution=command.refund_resolution.value,
                    return_value=return_value,
                    refunded_amount=refunded_amount,
                    reason=command.reason.strip(),
                    idempotency_key=command.idempotency_key,
                    request_fingerprint=fingerprint,
                )
                .returning(SaleReturn.id)
            )
            movement_prefix = hashlib.sha256(
                f"sale-return:{sale_return_id}".encode()
            ).hexdigest()

            for line in effective_lines:
                sold_line = lines_by_product[line.product_id]
                condition = (
                    StockCondition.AVAILABLE
                    if line.disposition is ReturnDisposition.RESTOCK
                    else StockCondition.DAMAGED
                )
                balance = connection.scalar(
                    postgresql_insert(StockBalance)
                    .values(
                        organization_id=command.organization_id,
                        product_id=line.product_id,
                        warehouse_id=sale.warehouse_id,
                        condition=condition.value,
                        quantity=line.quantity,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            StockBalance.organization_id,
                            StockBalance.product_id,
                            StockBalance.warehouse_id,
                            StockBalance.condition,
                        ],
                        set_={"quantity": StockBalance.quantity + line.quantity},
                    )
                    .returning(StockBalance.quantity)
                )
                line_value = sold_line.unit_price * line.quantity
                connection.execute(
                    insert(SaleReturnLine).values(
                        sale_return_id=sale_return_id,
                        product_id=line.product_id,
                        organization_id=command.organization_id,
                        sale_id=command.sale_id,
                        quantity=line.quantity,
                        disposition=line.disposition.value,
                        return_value=line_value,
                    )
                )
                connection.execute(
                    insert(StockMovement).values(
                        organization_id=command.organization_id,
                        product_id=line.product_id,
                        warehouse_id=sale.warehouse_id,
                        performed_by_id=command.processed_by_id,
                        sale_id=command.sale_id,
                        sale_return_id=sale_return_id,
                        stock_condition=condition.value,
                        movement_type=MovementType.RECEIPT.value,
                        quantity=line.quantity,
                        balance_after=balance,
                        reason=(
                            "Sale void"
                            if command.kind is ReturnKind.VOID
                            else "Customer return"
                        ),
                        reference=str(sale_return_id),
                        idempotency_key=f"{movement_prefix}:{line.product_id}",
                        request_fingerprint=fingerprint,
                    )
                )
    except IntegrityError as error:
        if (
            error.orig.diag.constraint_name
            != "uq_sale_returns_organization_idempotency_key"
        ):
            raise
        with engine.connect() as connection:
            replayed = _replayed_return(connection, command, fingerprint)
            if replayed is None:
                raise
            return replayed

    return SaleReturnResult(
        sale_return_id=sale_return_id,
        sale_id=command.sale_id,
        kind=command.kind,
        refund_resolution=command.refund_resolution,
        return_value=return_value,
        refunded_amount=refunded_amount,
        replayed=False,
    )
