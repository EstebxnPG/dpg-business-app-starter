from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Membership(Base):
    __tablename__ = "memberships"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approval_pin_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    approval_pin_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
