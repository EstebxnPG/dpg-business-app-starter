from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "invited_by_user_id"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_invitations_inviter_membership",
        ),
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        CheckConstraint(
            "role IN ('admin', 'warehouse_manager', 'salesperson')",
            name="ck_invitations_supported_role",
        ),
        Index(
            "ix_invitations_organization_email",
            "organization_id",
            "email",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
