"""index organization catalogs

Revision ID: b57d6e8a1c40
Revises: ebca4f0e3a2f
Create Date: 2026-10-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b57d6e8a1c40"
down_revision: Union[str, Sequence[str], None] = "ebca4f0e3a2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_products_organization_active_created",
        "products",
        ["organization_id", "active", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_warehouses_organization_active_created",
        "warehouses",
        ["organization_id", "active", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_warehouses_organization_active_created", table_name="warehouses")
    op.drop_index("ix_products_organization_active_created", table_name="products")
