from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.modules.inventory.router as inventory_router
from app.core.authorization import (
    CurrentMembership,
    OrganizationNotFoundError,
    get_current_membership,
)
from app.database import get_engine
from app.main import app
from app.modules.inventory.service import (
    IdempotencyConflictError,
    InsufficientStockError,
    MovementResult,
)


@pytest.fixture
def client():
    membership = CurrentMembership(
        organization_id=uuid4(),
        user_id=uuid4(),
        role="warehouse_manager",
    )
    app.dependency_overrides[get_engine] = lambda: object()
    app.dependency_overrides[get_current_membership] = lambda: membership
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def movement_request():
    return {
        "product_id": str(uuid4()),
        "warehouse_id": str(uuid4()),
        "movement_type": "RECEIPT",
        "quantity": "10",
        "reason": "Supplier delivery",
    }


def movement_headers():
    return {
        "Idempotency-Key": str(uuid4()),
        "X-Request-ID": "test-request-id",
    }


def test_create_movement_returns_created_result(client, monkeypatch) -> None:
    movement_id = uuid4()
    monkeypatch.setattr(
        inventory_router,
        "record_manual_stock_movement",
        lambda engine, membership, command: MovementResult(
            movement_id=movement_id,
            balance=Decimal("10"),
            replayed=False,
        ),
    )

    response = client.post(
        f"/organizations/{uuid4()}/inventory/movements",
        json=movement_request(),
        headers=movement_headers(),
    )

    assert response.status_code == 201
    assert response.json() == {
        "movement_id": str(movement_id),
        "balance": "10",
        "replayed": False,
    }
    assert response.headers["X-Request-ID"] == "test-request-id"


def test_replayed_movement_returns_original_result_with_ok_status(
    client, monkeypatch
) -> None:
    movement_id = uuid4()
    monkeypatch.setattr(
        inventory_router,
        "record_manual_stock_movement",
        lambda engine, membership, command: MovementResult(
            movement_id=movement_id,
            balance=Decimal("10"),
            replayed=True,
        ),
    )

    response = client.post(
        f"/organizations/{uuid4()}/inventory/movements",
        json=movement_request(),
        headers=movement_headers(),
    )

    assert response.status_code == 200
    assert response.json()["movement_id"] == str(movement_id)
    assert response.json()["replayed"] is True


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (InsufficientStockError(), "INSUFFICIENT_STOCK"),
        (IdempotencyConflictError(), "IDEMPOTENCY_KEY_REUSED"),
    ],
)
def test_business_errors_have_stable_contract(
    client, monkeypatch, exception, expected_code
) -> None:
    def raise_error(engine, membership, command):
        raise exception

    monkeypatch.setattr(inventory_router, "record_manual_stock_movement", raise_error)

    response = client.post(
        f"/organizations/{uuid4()}/inventory/movements",
        json=movement_request(),
        headers=movement_headers(),
    )

    assert response.status_code == 409
    assert response.json()["code"] == expected_code
    assert response.json()["request_id"] == "test-request-id"


def test_validation_errors_have_stable_contract(client) -> None:
    response = client.post(
        f"/organizations/{uuid4()}/inventory/movements",
        json={**movement_request(), "quantity": "0"},
        headers=movement_headers(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == "test-request-id"


def test_member_without_movement_permission_receives_forbidden(client) -> None:
    organization_id = uuid4()
    app.dependency_overrides[get_current_membership] = lambda: CurrentMembership(
        organization_id=organization_id,
        user_id=uuid4(),
        role="salesperson",
    )

    response = client.post(
        f"/organizations/{organization_id}/inventory/movements",
        json=movement_request(),
        headers=movement_headers(),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert response.json()["details"] == {"required_permission": "inventory:receive"}


def test_non_member_cannot_discover_organization(client) -> None:
    def hide_organization():
        raise OrganizationNotFoundError

    app.dependency_overrides[get_current_membership] = hide_organization

    response = client.post(
        f"/organizations/{uuid4()}/inventory/movements",
        json=movement_request(),
        headers=movement_headers(),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "ORGANIZATION_NOT_FOUND"
    assert response.json()["message"] == "The organization is unavailable."
