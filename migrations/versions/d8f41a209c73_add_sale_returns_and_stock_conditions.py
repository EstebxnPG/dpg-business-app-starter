"""add sale returns and stock conditions

Revision ID: d8f41a209c73
Revises: c341fd9258be
Create Date: 2026-10-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8f41a209c73"
down_revision: Union[str, Sequence[str], None] = "c341fd9258be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "stock_balances",
        sa.Column(
            "condition",
            sa.String(16),
            server_default="AVAILABLE",
            nullable=False,
        ),
    )
    op.drop_constraint("stock_balances_pkey", "stock_balances", type_="primary")
    op.create_primary_key(
        "stock_balances_pkey",
        "stock_balances",
        ["organization_id", "product_id", "warehouse_id", "condition"],
    )
    op.create_check_constraint(
        "ck_stock_balances_supported_condition",
        "stock_balances",
        "condition IN ('AVAILABLE', 'DAMAGED')",
    )

    op.add_column(
        "stock_movements",
        sa.Column(
            "stock_condition",
            sa.String(16),
            server_default="AVAILABLE",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_stock_movements_supported_condition",
        "stock_movements",
        "stock_condition IN ('AVAILABLE', 'DAMAGED')",
    )
    op.create_unique_constraint(
        "uq_sale_lines_organization_sale_product",
        "sale_lines",
        ["organization_id", "sale_id", "product_id"],
    )

    op.create_table(
        "sale_returns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("processed_by_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("refund_resolution", sa.String(24), nullable=False),
        sa.Column("return_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('RETURN', 'VOID')", name="ck_sale_returns_supported_kind"
        ),
        sa.CheckConstraint(
            "refund_resolution IN ('REFUNDED_NOW', 'NO_REFUND')",
            name="ck_sale_returns_refund_resolution",
        ),
        sa.CheckConstraint(
            "return_value >= 0", name="ck_sale_returns_nonnegative_value"
        ),
        sa.CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= return_value",
            name="ck_sale_returns_valid_refunded_amount",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "processed_by_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_sale_returns_processor_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sale_id"],
            ["sales.organization_id", "sales.id"],
            name="fk_sale_returns_sale_organization",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_sale_returns_organization_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_sale_returns_organization_idempotency_key",
        ),
    )
    op.create_index(
        "ix_sale_returns_sale_history",
        "sale_returns",
        ["organization_id", "sale_id", "created_at", "id"],
    )
    op.create_table(
        "sale_return_lines",
        sa.Column("sale_return_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("disposition", sa.String(16), nullable=False),
        sa.Column("return_value", sa.Numeric(20, 6), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_sale_return_lines_positive_quantity"
        ),
        sa.CheckConstraint(
            "disposition IN ('RESTOCK', 'DAMAGED')",
            name="ck_sale_return_lines_supported_disposition",
        ),
        sa.CheckConstraint(
            "return_value >= 0", name="ck_sale_return_lines_nonnegative_value"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sale_id", "product_id"],
            [
                "sale_lines.organization_id",
                "sale_lines.sale_id",
                "sale_lines.product_id",
            ],
            name="fk_sale_return_lines_sale_line",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sale_return_id"],
            ["sale_returns.organization_id", "sale_returns.id"],
            name="fk_sale_return_lines_return_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sale_return_id", "product_id"),
    )
    op.add_column(
        "stock_movements", sa.Column("sale_return_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_stock_movements_sale_return_organization",
        "stock_movements",
        "sale_returns",
        ["organization_id", "sale_return_id"],
        ["organization_id", "id"],
    )
    op.create_index(
        "ix_stock_movements_sale_return_id",
        "stock_movements",
        ["organization_id", "sale_return_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_movements_sale_return_id", table_name="stock_movements")
    op.drop_constraint(
        "fk_stock_movements_sale_return_organization",
        "stock_movements",
        type_="foreignkey",
    )
    op.drop_column("stock_movements", "sale_return_id")
    op.drop_table("sale_return_lines")
    op.drop_index("ix_sale_returns_sale_history", table_name="sale_returns")
    op.drop_table("sale_returns")
    op.drop_constraint(
        "uq_sale_lines_organization_sale_product", "sale_lines", type_="unique"
    )
    op.drop_constraint(
        "ck_stock_movements_supported_condition",
        "stock_movements",
        type_="check",
    )
    op.drop_column("stock_movements", "stock_condition")
    op.drop_constraint(
        "ck_stock_balances_supported_condition", "stock_balances", type_="check"
    )
    op.execute(
        """
        INSERT INTO stock_balances (
            organization_id, product_id, warehouse_id, condition, quantity
        )
        SELECT organization_id, product_id, warehouse_id, 'AVAILABLE',
               SUM(quantity)
        FROM stock_balances
        GROUP BY organization_id, product_id, warehouse_id
        ON CONFLICT (organization_id, product_id, warehouse_id, condition)
        DO UPDATE SET quantity = EXCLUDED.quantity
        """
    )
    op.execute("DELETE FROM stock_balances WHERE condition <> 'AVAILABLE'")
    op.drop_constraint("stock_balances_pkey", "stock_balances", type_="primary")
    op.create_primary_key(
        "stock_balances_pkey",
        "stock_balances",
        ["organization_id", "product_id", "warehouse_id"],
    )
    op.drop_column("stock_balances", "condition")
