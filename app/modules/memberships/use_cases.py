from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, select

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.modules.memberships.models import Membership
from app.modules.users.models import User


@dataclass(frozen=True)
class MemberItem:
    user_id: UUID
    email: str
    role: str
    active: bool


def list_members(engine: Engine, membership: CurrentMembership) -> list[MemberItem]:
    require_permission(membership, Permission.MEMBERS_MANAGE)
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                User.id.label("user_id"),
                User.email,
                Membership.role,
                User.active,
            )
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == membership.organization_id)
            .order_by(User.email, User.id)
        ).all()
    return [MemberItem(**row._mapping) for row in rows]
