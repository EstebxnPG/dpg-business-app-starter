import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, insert, select

from app.core.authorization import CurrentMembership
from app.core.security import CurrentUser, authenticate_user
from app.modules.invitations.models import OrganizationInvitation
from app.modules.invitations.use_cases import (
    ExistingUserAuthenticationRequiredError,
    InvalidInvitationError,
    accept_invitation,
    create_invitation,
)
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.users.models import User


def test_new_user_invitation_is_hashed_single_use_and_atomic() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_id = uuid4()
    admin_id = uuid4()
    invited_email = f"invited-{uuid4()}@example.com"
    password = "correct horse battery staple"

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Invitation Test")
        )
        connection.execute(
            insert(User).values(
                id=admin_id,
                email=f"{admin_id}@example.com",
                password_hash="not-used-by-this-test",
            )
        )
        connection.execute(
            insert(Membership).values(
                organization_id=organization_id,
                user_id=admin_id,
                role="admin",
            )
        )

    invited_user_id = None
    try:
        admin = CurrentMembership(organization_id, admin_id, "admin")
        invitation = create_invitation(
            engine, admin, invited_email, "warehouse_manager"
        )

        with engine.connect() as connection:
            stored_hash = connection.scalar(
                select(OrganizationInvitation.token_hash).where(
                    OrganizationInvitation.id == invitation.id
                )
            )
        assert (
            stored_hash
            == hashlib.sha256(invitation.acceptance_token.encode()).hexdigest()
        )
        assert stored_hash != invitation.acceptance_token

        accepted = accept_invitation(
            engine, invitation.acceptance_token, password, current_user=None
        )
        invited_user_id = accepted.user_id
        authenticated = authenticate_user(engine, invited_email, password)

        assert authenticated.id == invited_user_id
        assert accepted.role == "warehouse_manager"
        with pytest.raises(InvalidInvitationError):
            accept_invitation(
                engine, invitation.acceptance_token, password, current_user=None
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(OrganizationInvitation).where(
                    OrganizationInvitation.organization_id == organization_id
                )
            )
            connection.execute(
                delete(Membership).where(Membership.organization_id == organization_id)
            )
            connection.execute(
                delete(Organization).where(Organization.id == organization_id)
            )
            user_ids = [admin_id]
            if invited_user_id is not None:
                user_ids.append(invited_user_id)
            connection.execute(delete(User).where(User.id.in_(user_ids)))
        engine.dispose()


def test_existing_user_must_authenticate_to_join_another_organization() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_id = uuid4()
    admin_id = uuid4()
    existing_user_id = uuid4()
    existing_email = f"existing-{existing_user_id}@example.com"

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Second Company")
        )
        connection.execute(
            insert(User),
            [
                {
                    "id": admin_id,
                    "email": f"{admin_id}@example.com",
                    "password_hash": "not-used-by-this-test",
                },
                {
                    "id": existing_user_id,
                    "email": existing_email,
                    "password_hash": "not-used-by-this-test",
                },
            ],
        )
        connection.execute(
            insert(Membership).values(
                organization_id=organization_id,
                user_id=admin_id,
                role="admin",
            )
        )

    try:
        invitation = create_invitation(
            engine,
            CurrentMembership(organization_id, admin_id, "admin"),
            existing_email,
            "salesperson",
        )
        with pytest.raises(ExistingUserAuthenticationRequiredError):
            accept_invitation(
                engine, invitation.acceptance_token, password=None, current_user=None
            )

        accepted = accept_invitation(
            engine,
            invitation.acceptance_token,
            password=None,
            current_user=CurrentUser(existing_user_id, existing_email),
        )

        assert accepted.user_id == existing_user_id
        assert accepted.role == "salesperson"
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(OrganizationInvitation).where(
                    OrganizationInvitation.organization_id == organization_id
                )
            )
            connection.execute(
                delete(Membership).where(Membership.organization_id == organization_id)
            )
            connection.execute(
                delete(Organization).where(Organization.id == organization_id)
            )
            connection.execute(
                delete(User).where(User.id.in_([admin_id, existing_user_id]))
            )
        engine.dispose()
