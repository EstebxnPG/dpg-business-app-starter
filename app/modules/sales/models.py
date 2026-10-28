from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_sales_warehouse_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sold_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_sales_seller_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_sales_approver_membership",
        ),
        CheckConstraint("subtotal >= total", name="ck_sales_total_not_above_subtotal"),
        CheckConstraint("total >= 0", name="ck_sales_nonnegative_total"),
        CheckConstraint("cost_total >= 0", name="ck_sales_nonnegative_cost"),
        UniqueConstraint("organization_id", "id", name="uq_sales_organization_id"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_sales_organization_idempotency_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sold_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    approved_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    cost_total: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    approval_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SaleLine(Base):
    __tablename__ = "sale_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "sale_id"],
            ["sales.organization_id", "sales.id"],
            name="fk_sale_lines_sale_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_sale_lines_product_organization",
        ),
        CheckConstraint("quantity > 0", name="ck_sale_lines_positive_quantity"),
        CheckConstraint(
            "unit_price >= unit_cost", name="ck_sale_lines_price_covers_cost"
        ),
        CheckConstraint(
            "list_unit_price >= unit_price", name="ck_sale_lines_valid_discount"
        ),
        UniqueConstraint(
            "organization_id",
            "sale_id",
            "product_id",
            name="uq_sale_lines_organization_sale_product",
        ),
    )

    sale_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    product_sku: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    list_unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class SaleReturn(Base):
    __tablename__ = "sale_returns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "sale_id"],
            ["sales.organization_id", "sales.id"],
            name="fk_sale_returns_sale_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "processed_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_sale_returns_processor_membership",
        ),
        CheckConstraint(
            "kind IN ('RETURN', 'VOID')", name="ck_sale_returns_supported_kind"
        ),
        CheckConstraint(
            "refund_resolution IN ('REFUNDED_NOW', 'NO_REFUND')",
            name="ck_sale_returns_refund_resolution",
        ),
        CheckConstraint("return_value >= 0", name="ck_sale_returns_nonnegative_value"),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= return_value",
            name="ck_sale_returns_valid_refunded_amount",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_sale_returns_organization_id"
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_sale_returns_organization_idempotency_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sale_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    processed_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    refund_resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    return_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SaleReturnLine(Base):
    __tablename__ = "sale_return_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "sale_return_id"],
            ["sale_returns.organization_id", "sale_returns.id"],
            name="fk_sale_return_lines_return_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sale_id", "product_id"],
            [
                "sale_lines.organization_id",
                "sale_lines.sale_id",
                "sale_lines.product_id",
            ],
            name="fk_sale_return_lines_sale_line",
        ),
        CheckConstraint("quantity > 0", name="ck_sale_return_lines_positive_quantity"),
        CheckConstraint(
            "disposition IN ('RESTOCK', 'DAMAGED')",
            name="ck_sale_return_lines_supported_disposition",
        ),
        CheckConstraint(
            "return_value >= 0", name="ck_sale_return_lines_nonnegative_value"
        ),
    )

    sale_return_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sale_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    return_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
