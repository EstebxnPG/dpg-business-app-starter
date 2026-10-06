"""add organization invitations

Revision ID: c91a47e62b5d
Revises: b57d6e8a1c40
Create Date: 2026-10-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c91a47e62b5d"
down_revision: Union[str, Sequence[str], None] = "b57d6e8a1c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'warehouse_manager', 'salesperson')",
            name="ck_invitations_supported_role",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "invited_by_user_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_invitations_inviter_membership",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index(
        "ix_invitations_organization_email",
        "organization_invitations",
        ["organization_id", "email", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_invitations_organization_email",
        table_name="organization_invitations",
    )
    op.drop_table("organization_invitations")
