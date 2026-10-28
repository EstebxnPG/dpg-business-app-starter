from uuid import uuid4

from fastapi.testclient import TestClient

import app.modules.memberships.router as memberships_router
from app.core.authorization import CurrentMembership, get_current_membership
from app.database import get_engine
from app.main import app
from app.modules.memberships.use_cases import MemberItem


def test_admin_can_list_organization_members(monkeypatch) -> None:
    membership = CurrentMembership(uuid4(), uuid4(), "admin")
    member = MemberItem(
        user_id=uuid4(),
        email="seller@example.com",
        role="salesperson",
        active=True,
    )
    app.dependency_overrides[get_engine] = lambda: object()
    app.dependency_overrides[get_current_membership] = lambda: membership
    monkeypatch.setattr(memberships_router, "list_members", lambda *args: [member])

    try:
        response = TestClient(app).get(
            f"/organizations/{membership.organization_id}/members"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "user_id": str(member.user_id),
                "email": "seller@example.com",
                "role": "salesperson",
                "active": True,
            }
        ]
    }
