import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.core.security import CurrentUser, hash_password
from app.modules.invitations.models import OrganizationInvitation
from app.modules.memberships.models import Membership
from app.modules.users.models import User

INVITATION_LIFETIME_HOURS = 24
ALLOWED_ROLES = frozenset({"admin", "warehouse_manager", "salesperson"})


class InvalidInvitationError(Exception):
    pass


class ExistingUserAuthenticationRequiredError(Exception):
    pass


class InvitationMembershipConflictError(Exception):
    pass


@dataclass(frozen=True)
class InvitationCreated:
    id: UUID
    email: str
    role: str
    expires_at: datetime
    acceptance_token: str


@dataclass(frozen=True)
class InvitationAccepted:
    organization_id: UUID
    user_id: UUID
    role: str


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(
    engine: Engine,
    membership: CurrentMembership,
    email: str,
    role: str,
) -> InvitationCreated:
    require_permission(membership, Permission.MEMBERS_MANAGE)
    normalized_email = email.strip().lower()
    if role not in ALLOWED_ROLES:
        raise ValueError("Unsupported organization role")

    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=INVITATION_LIFETIME_HOURS)
    token = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        connection.execute(
            update(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == membership.organization_id,
                OrganizationInvitation.email == normalized_email,
                OrganizationInvitation.accepted_at.is_(None),
                OrganizationInvitation.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        row = connection.execute(
            insert(OrganizationInvitation)
            .values(
                organization_id=membership.organization_id,
                email=normalized_email,
                role=role,
                token_hash=_token_hash(token),
                invited_by_user_id=membership.user_id,
                expires_at=expires_at,
            )
            .returning(
                OrganizationInvitation.id,
                OrganizationInvitation.email,
                OrganizationInvitation.role,
                OrganizationInvitation.expires_at,
            )
        ).one()

    return InvitationCreated(
        **row._mapping,
        acceptance_token=token,
    )


def accept_invitation(
    engine: Engine,
    token: str,
    password: str | None,
    current_user: CurrentUser | None,
) -> InvitationAccepted:
    candidate_password_hash = hash_password(password) if password is not None else None
    now = datetime.now(UTC)

    try:
        with engine.begin() as connection:
            invitation = connection.execute(
                select(
                    OrganizationInvitation.id,
                    OrganizationInvitation.organization_id,
                    OrganizationInvitation.email,
                    OrganizationInvitation.role,
                    OrganizationInvitation.expires_at,
                    OrganizationInvitation.accepted_at,
                    OrganizationInvitation.revoked_at,
                )
                .where(OrganizationInvitation.token_hash == _token_hash(token))
                .with_for_update()
            ).one_or_none()
            if (
                invitation is None
                or invitation.accepted_at is not None
                or invitation.revoked_at is not None
                or invitation.expires_at <= now
            ):
                raise InvalidInvitationError

            existing_user = connection.execute(
                select(User.id, User.active).where(User.email == invitation.email)
            ).one_or_none()
            if existing_user is not None:
                if (
                    not existing_user.active
                    or current_user is None
                    or current_user.id != existing_user.id
                ):
                    raise ExistingUserAuthenticationRequiredError
                user_id = existing_user.id
            else:
                if current_user is not None or candidate_password_hash is None:
                    raise InvalidInvitationError
                user_id = connection.scalar(
                    insert(User)
                    .values(
                        email=invitation.email,
                        password_hash=candidate_password_hash,
                    )
                    .returning(User.id)
                )

            connection.execute(
                insert(Membership).values(
                    organization_id=invitation.organization_id,
                    user_id=user_id,
                    role=invitation.role,
                )
            )
            connection.execute(
                update(OrganizationInvitation)
                .where(OrganizationInvitation.id == invitation.id)
                .values(accepted_at=now)
            )
    except IntegrityError as error:
        if error.orig.diag.constraint_name == "memberships_pkey":
            raise InvitationMembershipConflictError from error
        if error.orig.diag.constraint_name == "users_email_key":
            raise ExistingUserAuthenticationRequiredError from error
        raise

    return InvitationAccepted(
        organization_id=invitation.organization_id,
        user_id=user_id,
        role=invitation.role,
    )
