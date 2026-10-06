from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.users.models import User


class BootstrapValidationError(ValueError):
    pass


class UserEmailConflictError(Exception):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    organization_id: UUID
    admin_user_id: UUID
    admin_email: str


def bootstrap_organization(
    engine: Engine,
    organization_name: str,
    admin_email: str,
    admin_password: str,
) -> BootstrapResult:
    normalized_name = organization_name.strip()
    normalized_email = admin_email.strip().lower()
    if not normalized_name:
        raise BootstrapValidationError("Organization name must not be blank")
    if "@" not in normalized_email:
        raise BootstrapValidationError("Administrator email is invalid")
    if len(admin_password) < 12:
        raise BootstrapValidationError(
            "Administrator password must contain at least 12 characters"
        )
    password_hash = hash_password(admin_password)

    try:
        with engine.begin() as connection:
            organization_id = connection.scalar(
                insert(Organization)
                .values(name=normalized_name)
                .returning(Organization.id)
            )
            user_id = connection.scalar(
                insert(User)
                .values(
                    email=normalized_email,
                    password_hash=password_hash,
                )
                .returning(User.id)
            )
            connection.execute(
                insert(Membership).values(
                    organization_id=organization_id,
                    user_id=user_id,
                    role="admin",
                )
            )
    except IntegrityError as error:
        if error.orig.diag.constraint_name == "users_email_key":
            raise UserEmailConflictError from error
        raise

    return BootstrapResult(
        organization_id=organization_id,
        admin_user_id=user_id,
        admin_email=normalized_email,
    )
