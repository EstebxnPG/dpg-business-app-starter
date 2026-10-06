import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, insert

from app.core.authorization import CurrentMembership, PermissionDeniedError
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.products.use_cases import (
    ProductSkuConflictError,
    create_product,
    list_products,
)
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse
from app.modules.warehouses.use_cases import (
    WarehouseCodeConflictError,
    create_warehouse,
    list_warehouses,
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
        product = create_product(engine, admin, " beauty-001 ", "Shampoo")
        warehouse = create_warehouse(engine, admin, " main ", "Main Warehouse")

        assert product.sku == "BEAUTY-001"
        assert warehouse.code == "MAIN"
        assert list_products(engine, salesperson, 50, None, False).items == [product]
        assert list_warehouses(engine, salesperson, 50, None, False).items == [
            warehouse
        ]

        with pytest.raises(ProductSkuConflictError):
            create_product(engine, admin, "BEAUTY-001", "Duplicate")
        with pytest.raises(WarehouseCodeConflictError):
            create_warehouse(engine, admin, "MAIN", "Duplicate")
        with pytest.raises(PermissionDeniedError):
            create_product(engine, salesperson, "BEAUTY-002", "Conditioner")
    finally:
        with engine.begin() as connection:
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
