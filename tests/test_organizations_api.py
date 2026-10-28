from uuid import uuid4

from fastapi.testclient import TestClient

import app.modules.organizations.router as organizations_router
from app.core.security import CurrentUser, get_current_user
from app.database import get_engine
from app.main import app
from app.modules.organizations.use_cases import OrganizationMembershipItem


def test_list_current_user_organizations(monkeypatch) -> None:
    user = CurrentUser(id=uuid4(), email="admin@example.com")
    organization_id = uuid4()
    captured = {}

    def list_organizations(engine, user_id):
        captured.update(engine=engine, user_id=user_id)
        return [
            OrganizationMembershipItem(
                id=organization_id,
                name="Beauty Store",
                role="admin",
                active=True,
            )
        ]

    engine = object()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        organizations_router,
        "list_user_organizations",
        list_organizations,
    )

    try:
        response = TestClient(app).get("/organizations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured == {"engine": engine, "user_id": user.id}
    assert response.json() == {
        "items": [
            {
                "id": str(organization_id),
                "name": "Beauty Store",
                "role": "admin",
                "active": True,
            }
        ]
    }
