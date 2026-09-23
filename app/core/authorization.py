import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from fastapi import Depends
from sqlalchemy import Engine, select

from app.core.security import CurrentUser, get_current_user
from app.database import get_engine
from app.modules.memberships.models import Membership

logger = logging.getLogger(__name__)


class Permission(StrEnum):
    INVENTORY_READ = "inventory:read"
    INVENTORY_RECEIVE = "inventory:receive"
    INVENTORY_ISSUE = "inventory:issue"
    INVENTORY_ADJUST = "inventory:adjust"
    CATALOG_MANAGE = "catalog:manage"
    MEMBERS_MANAGE = "members:manage"
    SALES_CREATE = "sales:create"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(Permission),
    "warehouse_manager": frozenset(
        {
            Permission.INVENTORY_READ,
            Permission.INVENTORY_RECEIVE,
            Permission.INVENTORY_ISSUE,
        }
    ),
    "salesperson": frozenset(
        {
            Permission.INVENTORY_READ,
            Permission.SALES_CREATE,
        }
    ),
}


class OrganizationNotFoundError(Exception):
    pass


class PermissionDeniedError(Exception):
    def __init__(self, permission: Permission) -> None:
        self.permission = permission


@dataclass(frozen=True)
class CurrentMembership:
    organization_id: UUID
    user_id: UUID
    role: str


def get_current_membership(
    organization_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    engine: Engine = Depends(get_engine),
) -> CurrentMembership:
    with engine.connect() as connection:
        role = connection.execute(
            select(Membership.role).where(
                Membership.organization_id == organization_id,
                Membership.user_id == current_user.id,
            )
        ).scalar_one_or_none()

    if role is None:
        logger.warning(
            "Organization access denied user_id=%s organization_id=%s",
            current_user.id,
            organization_id,
        )
        raise OrganizationNotFoundError

    return CurrentMembership(
        organization_id=organization_id,
        user_id=current_user.id,
        role=role,
    )


def require_permission(
    membership: CurrentMembership,
    permission: Permission,
) -> None:
    granted_permissions = ROLE_PERMISSIONS.get(membership.role, frozenset())
    if permission not in granted_permissions:
        logger.warning(
            "Permission denied user_id=%s organization_id=%s role=%s permission=%s",
            membership.user_id,
            membership.organization_id,
            membership.role,
            permission,
        )
        raise PermissionDeniedError(permission)
