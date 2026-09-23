"""add user password hashes

Revision ID: 79fb382ad528
Revises: 084ad680dd8a
Create Date: 2026-09-23 00:02:50.774067

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "79fb382ad528"
down_revision: Union[str, Sequence[str], None] = "084ad680dd8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "password_hash")
