"""index inventory movement history

Revision ID: ebca4f0e3a2f
Revises: 79fb382ad528
Create Date: 2026-09-28 15:33:41.116107

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ebca4f0e3a2f"
down_revision: Union[str, Sequence[str], None] = "79fb382ad528"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_stock_movements_inventory_history",
        "stock_movements",
        ["organization_id", "product_id", "warehouse_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_movements_inventory_history", table_name="stock_movements")
