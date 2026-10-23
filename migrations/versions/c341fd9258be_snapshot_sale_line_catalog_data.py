"""snapshot sale line catalog data

Revision ID: c341fd9258be
Revises: b92e14c670ad
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c341fd9258be"
down_revision: Union[str, Sequence[str], None] = "b92e14c670ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sale_lines", sa.Column("product_sku", sa.String(64), nullable=True))
    op.add_column(
        "sale_lines", sa.Column("product_name", sa.String(160), nullable=True)
    )
    op.execute(
        """
        UPDATE sale_lines
        SET product_sku = products.sku,
            product_name = products.name
        FROM products
        WHERE products.organization_id = sale_lines.organization_id
          AND products.id = sale_lines.product_id
        """
    )
    op.alter_column("sale_lines", "product_sku", nullable=False)
    op.alter_column("sale_lines", "product_name", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sale_lines", "product_name")
    op.drop_column("sale_lines", "product_sku")
