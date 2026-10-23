"""add atomic stock transfers

Revision ID: a71c93f48b2d
Revises: d2468ac735ef
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a71c93f48b2d"
down_revision: Union[str, Sequence[str], None] = "d2468ac735ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("source_warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("destination_warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("performed_by_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("source_balance_after", sa.Numeric(20, 6), nullable=False),
        sa.Column("destination_balance_after", sa.Numeric(20, 6), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_warehouse_id <> destination_warehouse_id",
            name="ck_stock_transfers_distinct_warehouses",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_stock_transfers_positive_quantity"),
        sa.ForeignKeyConstraint(
            ["organization_id", "destination_warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_transfers_destination_warehouse_organization",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "performed_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_stock_transfers_performer_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_stock_transfers_product_organization",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_transfers_source_warehouse_organization",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_stock_transfers_organization_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_stock_transfers_organization_idempotency_key",
        ),
    )
    op.add_column("stock_movements", sa.Column("transfer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_stock_movements_transfer_organization",
        "stock_movements",
        "stock_transfers",
        ["organization_id", "transfer_id"],
        ["organization_id", "id"],
    )
    op.create_index(
        "ix_stock_movements_transfer_id",
        "stock_movements",
        ["organization_id", "transfer_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_movements_transfer_id", table_name="stock_movements")
    op.drop_constraint(
        "fk_stock_movements_transfer_organization",
        "stock_movements",
        type_="foreignkey",
    )
    op.drop_column("stock_movements", "transfer_id")
    op.drop_table("stock_transfers")
