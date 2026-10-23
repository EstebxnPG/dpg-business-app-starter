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
