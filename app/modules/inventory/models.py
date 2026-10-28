from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_stock_balances_product_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_balances_warehouse_organization",
        ),
        CheckConstraint("quantity >= 0", name="ck_stock_balances_nonnegative"),
        CheckConstraint(
            "condition IN ('AVAILABLE', 'DAMAGED')",
            name="ck_stock_balances_supported_condition",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    condition: Mapped[str] = mapped_column(
        String(16), primary_key=True, server_default=text("AVAILABLE")
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, server_default=text("0")
    )


class StockTransfer(Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_stock_transfers_product_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_transfers_source_warehouse_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "destination_warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_transfers_destination_warehouse_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "performed_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_stock_transfers_performer_membership",
        ),
        CheckConstraint("quantity > 0", name="ck_stock_transfers_positive_quantity"),
        CheckConstraint(
            "source_warehouse_id <> destination_warehouse_id",
            name="ck_stock_transfers_distinct_warehouses",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_stock_transfers_organization_id"
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_stock_transfers_organization_idempotency_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_warehouse_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    destination_warehouse_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    performed_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    source_balance_after: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False
    )
    destination_balance_after: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_stock_movements_product_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_movements_warehouse_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "performed_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_stock_movements_performer_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "transfer_id"],
            ["stock_transfers.organization_id", "stock_transfers.id"],
            name="fk_stock_movements_transfer_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sale_id"],
            ["sales.organization_id", "sales.id"],
            name="fk_stock_movements_sale_organization",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sale_return_id"],
            ["sale_returns.organization_id", "sale_returns.id"],
            name="fk_stock_movements_sale_return_organization",
        ),
        CheckConstraint("quantity > 0", name="ck_stock_movements_positive_quantity"),
        CheckConstraint(
            "movement_type IN ('RECEIPT', 'ISSUE')",
            name="ck_stock_movements_supported_type",
        ),
        CheckConstraint(
            "stock_condition IN ('AVAILABLE', 'DAMAGED')",
            name="ck_stock_movements_supported_condition",
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_stock_movements_organization_idempotency_key",
        ),
        Index(
            "ix_stock_movements_inventory_history",
            "organization_id",
            "product_id",
            "warehouse_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    performed_by_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    transfer_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    sale_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    sale_return_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    stock_condition: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("AVAILABLE")
    )
    movement_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
