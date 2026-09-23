"""add stock balances with organization constraints

Revision ID: 388e4e4b18b6
Revises: 4ef93078d013
Create Date: 2026-09-18 16:37:36.811973

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "388e4e4b18b6"
down_revision: Union[str, Sequence[str], None] = "4ef93078d013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_products_organization_id", "products", ["organization_id", "id"]
    )
    op.create_unique_constraint(
        "uq_warehouses_organization_id", "warehouses", ["organization_id", "id"]
    )
    op.create_table(
        "stock_balances",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column(
            "quantity",
            sa.Numeric(precision=20, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_balances_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_stock_balances_product_organization",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "warehouse_id"],
            ["warehouses.organization_id", "warehouses.id"],
            name="fk_stock_balances_warehouse_organization",
        ),
        sa.PrimaryKeyConstraint("organization_id", "product_id", "warehouse_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("stock_balances")
    op.drop_constraint("uq_warehouses_organization_id", "warehouses", type_="unique")
    op.drop_constraint("uq_products_organization_id", "products", type_="unique")
