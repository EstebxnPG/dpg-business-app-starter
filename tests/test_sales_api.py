from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.modules.sales.router as sales_router
from app.core.authorization import CurrentMembership, get_current_membership
from app.database import get_engine
from app.main import app
from app.modules.sales.service import (
    DiscountApprovalRequiredError,
    SaleInsufficientStockError,
    SalePriceBelowCostError,
    SaleResult,
)


@pytest.fixture
def client():
    membership = CurrentMembership(uuid4(), uuid4(), "salesperson")
    app.dependency_overrides[get_engine] = lambda: object()
    app.dependency_overrides[get_current_membership] = lambda: membership
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def sale_request():
    return {
        "warehouse_id": str(uuid4()),
        "lines": [{"product_id": str(uuid4()), "quantity": "2", "unit_price": "18000"}],
        "discount_reason": "Customer negotiation",
    }


def test_create_sale_returns_financial_snapshot(client, monkeypatch) -> None:
    sale_id = uuid4()
    monkeypatch.setattr(
        sales_router,
        "submit_sale",
        lambda *args: SaleResult(
            sale_id=sale_id,
            subtotal=Decimal("40000"),
            discount_total=Decimal("4000"),
            total=Decimal("36000"),
            cost_total=Decimal("24000"),
            approved_by_id=None,
            replayed=False,
        ),
    )

    response = client.post(
        f"/organizations/{uuid4()}/sales",
        json=sale_request(),
        headers={"Idempotency-Key": "sale-1"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "sale_id": str(sale_id),
        "subtotal": "40000",
        "discount_total": "4000",
        "total": "36000",
        "cost_total": "24000",
        "approved_by_id": None,
        "replayed": False,
    }


def test_replayed_sale_returns_ok(client, monkeypatch) -> None:
    monkeypatch.setattr(
        sales_router,
        "submit_sale",
        lambda *args: SaleResult(
            uuid4(),
            Decimal("20000"),
            Decimal("0"),
            Decimal("20000"),
            Decimal("12000"),
            None,
            True,
        ),
    )
    response = client.post(
        f"/organizations/{uuid4()}/sales",
        json=sale_request(),
        headers={"Idempotency-Key": "sale-replay"},
    )
    assert response.status_code == 200
    assert response.json()["replayed"] is True


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (SalePriceBelowCostError(), 409, "SALE_PRICE_BELOW_COST"),
        (DiscountApprovalRequiredError(), 409, "DISCOUNT_APPROVAL_REQUIRED"),
        (SaleInsufficientStockError(uuid4()), 409, "INSUFFICIENT_STOCK"),
    ],
)
def test_sale_errors_have_stable_contract(
    client, monkeypatch, error, status_code, code
) -> None:
    def raise_error(*args):
        raise error

    monkeypatch.setattr(sales_router, "submit_sale", raise_error)
    response = client.post(
        f"/organizations/{uuid4()}/sales",
        json=sale_request(),
        headers={"Idempotency-Key": "failed-sale", "X-Request-ID": "sale-error"},
    )
    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert response.json()["request_id"] == "sale-error"


def test_sale_rejects_duplicate_product_lines(client) -> None:
    payload = sale_request()
    payload["lines"].append(payload["lines"][0])
    response = client.post(
        f"/organizations/{uuid4()}/sales",
        json=payload,
        headers={"Idempotency-Key": "duplicate-lines"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_admin_can_configure_policy_and_personal_pin(client, monkeypatch) -> None:
    app.dependency_overrides[get_current_membership] = lambda: CurrentMembership(
        uuid4(), uuid4(), "admin"
    )
    captured = {}
    monkeypatch.setattr(
        sales_router,
        "update_sales_policy",
        lambda engine, membership, rate: rate,
    )

    def configure_pin(engine, membership, pin):
        captured["pin"] = pin

    monkeypatch.setattr(sales_router, "set_approval_pin", configure_pin)

    policy = client.patch(
        f"/organizations/{uuid4()}/sales/policy",
        json={"salesperson_max_discount_rate": "0.075"},
    )
    pin = client.put(
        f"/organizations/{uuid4()}/sales/approval-pin",
        json={"pin": "123456"},
    )

    assert policy.status_code == 200
    assert policy.json()["salesperson_max_discount_rate"] == "0.075"
    assert pin.status_code == 200
    assert captured["pin"] == "123456"
