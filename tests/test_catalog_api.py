from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.modules.products.router as products_router
import app.modules.warehouses.router as warehouses_router
from app.core.authorization import CurrentMembership, get_current_membership
from app.database import get_engine
from app.main import app
from app.modules.products.use_cases import ProductItem, ProductPage
from app.modules.warehouses.use_cases import WarehouseItem, WarehousePage


@pytest.fixture
def client():
    membership = CurrentMembership(
        organization_id=uuid4(),
        user_id=uuid4(),
        role="admin",
    )
    app.dependency_overrides[get_engine] = lambda: object()
    app.dependency_overrides[get_current_membership] = lambda: membership
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_product_normalizes_catalog_values(client, monkeypatch) -> None:
    product_id = uuid4()
    captured = {}

    def create(engine, membership, sku, name):
        captured.update(sku=sku, name=name)
        return ProductItem(
            id=product_id,
            sku=sku,
            name=name,
            active=True,
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
        )

    monkeypatch.setattr(products_router, "create_product", create)
    response = client.post(
        f"/organizations/{uuid4()}/products",
        json={"sku": "  beauty-001 ", "name": "  Shampoo Repair  "},
    )

    assert response.status_code == 201
    assert captured == {"sku": "BEAUTY-001", "name": "Shampoo Repair"}
    assert response.json()["id"] == str(product_id)


def test_list_products_returns_cursor_page(client, monkeypatch) -> None:
    product_id = uuid4()
    next_cursor = uuid4()
    monkeypatch.setattr(
        products_router,
        "list_products",
        lambda *args: ProductPage(
            items=[
                ProductItem(
                    id=product_id,
                    sku="BEAUTY-001",
                    name="Shampoo Repair",
                    active=True,
                    created_at=datetime(2026, 10, 5, tzinfo=UTC),
                )
            ],
            next_cursor=next_cursor,
        ),
    )

    response = client.get(f"/organizations/{uuid4()}/products")

    assert response.status_code == 200
    assert response.json()["items"][0]["sku"] == "BEAUTY-001"
    assert response.json()["next_cursor"] == str(next_cursor)


def test_create_and_list_warehouse_contracts(client, monkeypatch) -> None:
    warehouse_id = uuid4()
    item = WarehouseItem(
        id=warehouse_id,
        code="MAIN",
        name="Main Warehouse",
        active=True,
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )
    monkeypatch.setattr(warehouses_router, "create_warehouse", lambda *args: item)
    monkeypatch.setattr(
        warehouses_router,
        "list_warehouses",
        lambda *args: WarehousePage(items=[item], next_cursor=None),
    )

    created = client.post(
        f"/organizations/{uuid4()}/warehouses",
        json={"code": " main ", "name": " Main Warehouse "},
    )
    listed = client.get(f"/organizations/{uuid4()}/warehouses")

    assert created.status_code == 201
    assert created.json()["code"] == "MAIN"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == str(warehouse_id)
