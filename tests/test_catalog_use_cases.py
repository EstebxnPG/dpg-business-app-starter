import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, insert

from app.core.authorization import CurrentMembership, PermissionDeniedError
from app.modules.inventory.models import StockBalance
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.products.use_cases import (
    ProductHasStockError,
    ProductSkuConflictError,
    create_product,
    get_product,
    list_products,
    update_product,
)
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse
from app.modules.warehouses.use_cases import (
    WarehouseCodeConflictError,
    WarehouseHasStockError,
    create_warehouse,
    get_warehouse,
    list_warehouses,
    update_warehouse,
)


def test_catalog_creation_listing_and_permissions() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_id = uuid4()
    admin_id = uuid4()
    salesperson_id = uuid4()
    admin = CurrentMembership(organization_id, admin_id, "admin")
    salesperson = CurrentMembership(organization_id, salesperson_id, "salesperson")

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Catalog Test")
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
                    "id": salesperson_id,
                    "email": f"{salesperson_id}@example.com",
                    "password_hash": "not-used-by-this-test",
                },
            ],
        )
        connection.execute(
            insert(Membership),
            [
                {
                    "organization_id": organization_id,
                    "user_id": admin_id,
                    "role": "admin",
                },
                {
                    "organization_id": organization_id,
                    "user_id": salesperson_id,
                    "role": "salesperson",
                },
            ],
        )

    try:
        product = create_product(
            engine, admin, " beauty-001 ", "Shampoo", Decimal("12000"), Decimal("20000")
        )
        warehouse = create_warehouse(engine, admin, " main ", "Main Warehouse")

        assert product.sku == "BEAUTY-001"
        assert warehouse.code == "MAIN"
        assert list_products(engine, salesperson, 50, None, False, None).items == [
            product
        ]
        assert list_warehouses(engine, salesperson, 50, None, False, None).items == [
            warehouse
        ]
        assert get_product(engine, salesperson, product.id) == product
        assert get_warehouse(engine, salesperson, warehouse.id) == warehouse

        updated_product = update_product(
            engine, admin, product.id, "Updated Shampoo", None, None, None
        )
        updated_warehouse = update_warehouse(
            engine, admin, warehouse.id, "Updated Warehouse", None
        )
        assert updated_product.name == "Updated Shampoo"
        assert updated_warehouse.name == "Updated Warehouse"

        with engine.begin() as connection:
            connection.execute(
                insert(StockBalance).values(
                    organization_id=organization_id,
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity=1,
                )
            )
        with pytest.raises(ProductHasStockError):
            update_product(engine, admin, product.id, None, False, None, None)
        with pytest.raises(WarehouseHasStockError):
            update_warehouse(engine, admin, warehouse.id, None, False)

        with engine.begin() as connection:
            connection.execute(
                delete(StockBalance).where(
                    StockBalance.organization_id == organization_id
                )
            )
        assert (
            update_product(engine, admin, product.id, None, False, None, None).active
            is False
        )
        assert (
            update_warehouse(engine, admin, warehouse.id, None, False).active is False
        )

        with pytest.raises(ProductSkuConflictError):
            create_product(
                engine,
                admin,
                "BEAUTY-001",
                "Duplicate",
                Decimal("12000"),
                Decimal("20000"),
            )
        with pytest.raises(WarehouseCodeConflictError):
            create_warehouse(engine, admin, "MAIN", "Duplicate")
        with pytest.raises(PermissionDeniedError):
            create_product(
                engine,
                salesperson,
                "BEAUTY-002",
                "Conditioner",
                Decimal("8000"),
                Decimal("15000"),
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(StockBalance).where(
                    StockBalance.organization_id == organization_id
                )
            )
            connection.execute(
                delete(Product).where(Product.organization_id == organization_id)
            )
            connection.execute(
                delete(Warehouse).where(Warehouse.organization_id == organization_id)
            )
            connection.execute(
                delete(Membership).where(Membership.organization_id == organization_id)
            )
            connection.execute(
                delete(Organization).where(Organization.id == organization_id)
            )
            connection.execute(
                delete(User).where(User.id.in_([admin_id, salesperson_id]))
            )
        engine.dispose()
