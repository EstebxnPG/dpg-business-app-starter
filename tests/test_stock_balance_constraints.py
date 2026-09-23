import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.exc import IntegrityError

from app.modules.inventory.models import StockBalance
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.warehouses.models import Warehouse


def test_stock_balance_enforces_organization_and_nonnegative_quantity() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_a = uuid4()
    organization_b = uuid4()
    product_a = uuid4()
    product_b = uuid4()
    warehouse_a = uuid4()
    warehouse_b = uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                insert(Organization),
                [
                    {"id": organization_a, "name": "Organization A"},
                    {"id": organization_b, "name": "Organization B"},
                ],
            )
            connection.execute(
                insert(Product),
                [
                    {
                        "id": product_a,
                        "organization_id": organization_a,
                        "sku": "PRODUCT-A",
                        "name": "Product A",
                    },
                    {
                        "id": product_b,
                        "organization_id": organization_b,
                        "sku": "PRODUCT-B",
                        "name": "Product B",
                    },
                ],
            )
            connection.execute(
                insert(Warehouse),
                [
                    {
                        "id": warehouse_a,
                        "organization_id": organization_a,
                        "code": "WAREHOUSE-A",
                        "name": "Warehouse A",
                    },
                    {
                        "id": warehouse_b,
                        "organization_id": organization_b,
                        "code": "WAREHOUSE-B",
                        "name": "Warehouse B",
                    },
                ],
            )
            connection.execute(
                insert(StockBalance).values(
                    organization_id=organization_a,
                    product_id=product_a,
                    warehouse_id=warehouse_a,
                    quantity=Decimal("10"),
                )
            )

            invalid_pairs = (
                (
                    {"product_id": product_a, "warehouse_id": warehouse_b},
                    "fk_stock_balances_warehouse_organization",
                ),
                (
                    {"product_id": product_b, "warehouse_id": warehouse_a},
                    "fk_stock_balances_product_organization",
                ),
            )
            for invalid_pair, expected_constraint in invalid_pairs:
                with pytest.raises(IntegrityError) as error:
                    with connection.begin_nested():
                        connection.execute(
                            insert(StockBalance).values(
                                organization_id=organization_a,
                                quantity=Decimal("1"),
                                **invalid_pair,
                            )
                        )
                assert error.value.orig.diag.constraint_name == expected_constraint

            with pytest.raises(IntegrityError) as error:
                with connection.begin_nested():
                    connection.execute(
                        insert(StockBalance).values(
                            organization_id=organization_b,
                            product_id=product_b,
                            warehouse_id=warehouse_b,
                            quantity=Decimal("-1"),
                        )
                    )
            assert (
                error.value.orig.diag.constraint_name == "ck_stock_balances_nonnegative"
            )

            quantity = connection.scalar(
                select(StockBalance.quantity).where(
                    StockBalance.organization_id == organization_a,
                    StockBalance.product_id == product_a,
                    StockBalance.warehouse_id == warehouse_a,
                )
            )
            assert quantity == Decimal("10")
        finally:
            transaction.rollback()
