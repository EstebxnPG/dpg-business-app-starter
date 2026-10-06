import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, select

from app.core.security import authenticate_user
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.organizations.use_cases import (
    BootstrapValidationError,
    UserEmailConflictError,
    bootstrap_organization,
)
from app.modules.users.models import User


def test_bootstrap_validates_input_before_database_access() -> None:
    with pytest.raises(BootstrapValidationError):
        bootstrap_organization(object(), " ", "admin@example.com", "long-password")
    with pytest.raises(BootstrapValidationError):
        bootstrap_organization(object(), "DPG", "invalid-email", "long-password")
    with pytest.raises(BootstrapValidationError):
        bootstrap_organization(object(), "DPG", "admin@example.com", "short")


def test_bootstrap_creates_authenticatable_admin_atomically() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    marker = uuid4()
    organization_name = f"Bootstrap Test {marker}"
    email = f"bootstrap-{marker}@example.com"
    password = "correct horse battery staple"
    result = None

    try:
        result = bootstrap_organization(engine, organization_name, email, password)
        authenticated = authenticate_user(engine, email, password)

        with engine.connect() as connection:
            role = connection.scalar(
                select(Membership.role).where(
                    Membership.organization_id == result.organization_id,
                    Membership.user_id == result.admin_user_id,
                )
            )

        assert authenticated.id == result.admin_user_id
        assert role == "admin"

        with pytest.raises(UserEmailConflictError):
            bootstrap_organization(engine, f"Duplicate {marker}", email, password)

        with engine.connect() as connection:
            rolled_back_organization_count = connection.scalar(
                select(func.count())
                .select_from(Organization)
                .where(Organization.name == f"Duplicate {marker}")
            )
        assert rolled_back_organization_count == 0
    finally:
        if result is not None:
            with engine.begin() as connection:
                connection.execute(
                    delete(Membership).where(
                        Membership.organization_id == result.organization_id
                    )
                )
                connection.execute(
                    delete(Organization).where(
                        Organization.id == result.organization_id
                    )
                )
                connection.execute(delete(User).where(User.id == result.admin_user_id))
        engine.dispose()
