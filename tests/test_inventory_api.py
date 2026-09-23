from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.modules.inventory.router as inventory_router
from app.core.security import CurrentUser, get_current_user
from app.database import get_engine
from app.main import app
from app.modules.inventory.service import (
    IdempotencyConflictError,
    InsufficientStockError,
    MovementResult,
)


@pytest.fixture
def client():
    app.dependency_overrides[get_engine] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), email="operator@example.com"
    )
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
        "record_stock_movement",
        lambda engine, command: MovementResult(
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
        "record_stock_movement",
        lambda engine, command: MovementResult(
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
    def raise_error(engine, command):
        raise exception

    monkeypatch.setattr(inventory_router, "record_stock_movement", raise_error)

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
