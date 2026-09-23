import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, insert

from app.core.security import hash_password
from app.main import app
from app.modules.users.models import User

TEST_PASSWORD = "correct horse battery staple"
TEST_SECRET = "test-secret-key-with-at-least-32-characters"


@pytest.fixture
def auth_user(monkeypatch):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    engine = create_engine(database_url)
    user_id = uuid4()
    email = f"auth-{user_id}@example.com"

    with engine.begin() as connection:
        connection.execute(
            insert(User).values(
                id=user_id,
                email=email,
                password_hash=hash_password(TEST_PASSWORD),
            )
        )

    try:
        yield {"id": user_id, "email": email}
    finally:
        with engine.begin() as connection:
            connection.execute(delete(User).where(User.id == user_id))
        engine.dispose()


def test_login_issues_token_that_identifies_active_user(auth_user) -> None:
    with TestClient(app) as client:
        login_response = client.post(
            "/auth/token",
            json={"email": auth_user["email"], "password": TEST_PASSWORD},
        )

        assert login_response.status_code == 200
        token_data = login_response.json()
        assert token_data["token_type"] == "bearer"
        assert token_data["expires_in"] == 1800

        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )

    assert me_response.status_code == 200
    assert me_response.json() == {
        "id": str(auth_user["id"]),
        "email": auth_user["email"],
    }


def test_login_rejects_wrong_password_without_revealing_why(auth_user) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/auth/token",
            json={"email": auth_user["email"], "password": "incorrect-password"},
            headers={"X-Request-ID": "invalid-login"},
        )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {
        "code": "INVALID_CREDENTIALS",
        "message": "The credentials are invalid or expired.",
        "details": {},
        "request_id": "invalid-login",
    }


def test_me_rejects_tampered_token(auth_user) -> None:
    with TestClient(app) as client:
        login_response = client.post(
            "/auth/token",
            json={"email": auth_user["email"], "password": TEST_PASSWORD},
        )
        token = login_response.json()["access_token"]

        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token[:-1]}x"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_me_requires_bearer_token(auth_user) -> None:
    with TestClient(app) as client:
        response = client.get("/auth/me", headers={"X-Request-ID": "missing-token"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert response.json()["request_id"] == "missing-token"
