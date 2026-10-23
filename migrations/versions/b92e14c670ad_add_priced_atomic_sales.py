"""add priced atomic sales

Revision ID: b92e14c670ad
Revises: a71c93f48b2d
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b92e14c670ad"
down_revision: Union[str, Sequence[str], None] = "a71c93f48b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "products",
        sa.Column("cost", sa.Numeric(20, 6), server_default="0", nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("sale_price", sa.Numeric(20, 6), server_default="0", nullable=False),
    )
    op.create_check_constraint("ck_products_nonnegative_cost", "products", "cost >= 0")
    op.create_check_constraint(
        "ck_products_price_not_below_cost", "products", "sale_price >= cost"
    )
    op.add_column(
        "organizations",
        sa.Column(
            "salesperson_max_discount_rate",
            sa.Numeric(5, 4),
            server_default="0.1000",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_organizations_salesperson_discount_rate",
        "organizations",
        "salesperson_max_discount_rate >= 0 AND salesperson_max_discount_rate <= 1",
    )
    op.add_column(
        "memberships", sa.Column("approval_pin_hash", sa.String(255), nullable=True)
    )
    op.add_column(
        "memberships",
        sa.Column(
            "approval_pin_failures", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "approval_pin_locked_until", sa.DateTime(timezone=True), nullable=True
        ),
    )

    op.create_table(
        "sales",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("sold_by_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("subtotal", sa.Numeric(20, 6), nullable=False),
        sa.Column("discount_total", sa.Numeric(20, 6), nullable=False),
        sa.Column("total", sa.Numeric(20, 6), nullable=False),
        sa.Column("cost_total", sa.Numeric(20, 6), nullable=False),
        sa.Column("approval_reason", sa.String(240), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subtotal >= total", name="ck_sales_total_not_above_subtotal"
        ),
        sa.CheckConstraint("total >= 0", name="ck_sales_nonnegative_total"),
        sa.CheckConstraint("cost_total >= 0", name="ck_sales_nonnegative_cost"),
        sa.ForeignKeyConstraint(
            ["organization_id", "approved_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_sales_approver_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sold_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_sales_seller_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_sales_warehouse_organization",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_sales_organization_id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_sales_organization_idempotency_key",
        ),
    )
    op.create_table(
        "sale_lines",
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("list_unit_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit_cost", sa.Numeric(20, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(20, 6), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_lines_positive_quantity"),
        sa.CheckConstraint(
            "unit_price >= unit_cost", name="ck_sale_lines_price_covers_cost"
        ),
        sa.CheckConstraint(
            "list_unit_price >= unit_price", name="ck_sale_lines_valid_discount"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_sale_lines_product_organization",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sale_id"],
            ["sales.organization_id", "sales.id"],
            name="fk_sale_lines_sale_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sale_id", "product_id"),
    )
    op.add_column("stock_movements", sa.Column("sale_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_stock_movements_sale_organization",
        "stock_movements",
        "sales",
        ["organization_id", "sale_id"],
        ["organization_id", "id"],
    )
    op.create_index(
        "ix_stock_movements_sale_id", "stock_movements", ["organization_id", "sale_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_movements_sale_id", table_name="stock_movements")
    op.drop_constraint(
        "fk_stock_movements_sale_organization", "stock_movements", type_="foreignkey"
    )
    op.drop_column("stock_movements", "sale_id")
    op.drop_table("sale_lines")
    op.drop_table("sales")
    op.drop_column("memberships", "approval_pin_locked_until")
    op.drop_column("memberships", "approval_pin_failures")
    op.drop_column("memberships", "approval_pin_hash")
    op.drop_constraint(
        "ck_organizations_salesperson_discount_rate", "organizations", type_="check"
    )
    op.drop_column("organizations", "salesperson_max_discount_rate")
    op.drop_constraint("ck_products_price_not_below_cost", "products", type_="check")
    op.drop_constraint("ck_products_nonnegative_cost", "products", type_="check")
    op.drop_column("products", "sale_price")
    op.drop_column("products", "cost")
