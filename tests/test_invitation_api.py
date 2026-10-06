from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.modules.invitations.router as invitations_router
from app.core.authorization import CurrentMembership, get_current_membership
from app.core.security import get_optional_current_user
from app.database import get_engine
from app.main import app
from app.modules.invitations.use_cases import (
    ExistingUserAuthenticationRequiredError,
    InvalidInvitationError,
    InvitationAccepted,
    InvitationCreated,
)


@pytest.fixture
def client():
    app.dependency_overrides[get_engine] = lambda: object()
    app.dependency_overrides[get_current_membership] = lambda: CurrentMembership(
        organization_id=uuid4(), user_id=uuid4(), role="admin"
    )
    app.dependency_overrides[get_optional_current_user] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_admin_creates_invitation_and_receives_token_once(client, monkeypatch) -> None:
    invitation_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    monkeypatch.setattr(
        invitations_router,
        "create_invitation",
        lambda *args: InvitationCreated(
            id=invitation_id,
            email="operator@example.com",
            role="warehouse_manager",
            expires_at=expires_at,
            acceptance_token="temporary-acceptance-token-with-enough-length",
        ),
    )

    response = client.post(
        f"/organizations/{uuid4()}/invitations",
        json={"email": " Operator@Example.com ", "role": "warehouse_manager"},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "operator@example.com"
    assert response.json()["acceptance_token"].startswith("temporary-")


def test_new_user_accepts_invitation(client, monkeypatch) -> None:
    accepted = InvitationAccepted(
        organization_id=uuid4(), user_id=uuid4(), role="salesperson"
    )
    monkeypatch.setattr(invitations_router, "accept_invitation", lambda *args: accepted)

    response = client.post(
        "/invitations/accept",
        json={
            "token": "temporary-acceptance-token-with-enough-length",
            "password": "correct horse battery staple",
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(accepted.user_id)
    assert response.json()["role"] == "salesperson"


@pytest.mark.parametrize(
    ("exception", "status_code", "code"),
    [
        (InvalidInvitationError(), 400, "INVITATION_INVALID"),
        (
            ExistingUserAuthenticationRequiredError(),
            401,
            "INVITATION_LOGIN_REQUIRED",
        ),
    ],
)
def test_invitation_errors_have_stable_contract(
    client, monkeypatch, exception, status_code, code
) -> None:
    def fail(*args):
        raise exception

    monkeypatch.setattr(invitations_router, "accept_invitation", fail)

    response = client.post(
        "/invitations/accept",
        json={"token": "invalid-invitation-token-with-enough-length"},
        headers={"X-Request-ID": "invitation-error"},
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert response.json()["request_id"] == "invitation-error"
    if status_code == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"
