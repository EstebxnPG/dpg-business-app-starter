"""add movement idempotency

Revision ID: 084ad680dd8a
Revises: ea064ed6013d
Create Date: 2026-09-22 22:35:40.669794

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "084ad680dd8a"
down_revision: Union[str, Sequence[str], None] = "ea064ed6013d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "stock_movements",
        sa.Column("balance_after", sa.Numeric(precision=20, scale=6), nullable=False),
    )
    op.add_column(
        "stock_movements",
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
    )
    op.add_column(
        "stock_movements",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
    )
    op.create_unique_constraint(
        "uq_stock_movements_organization_idempotency_key",
        "stock_movements",
        ["organization_id", "idempotency_key"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_stock_movements_organization_idempotency_key",
        "stock_movements",
        type_="unique",
    )
    op.drop_column("stock_movements", "request_fingerprint")
    op.drop_column("stock_movements", "idempotency_key")
    op.drop_column("stock_movements", "balance_after")
