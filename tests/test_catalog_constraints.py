import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.warehouses.models import Warehouse


@pytest.mark.parametrize(
    ("model", "code_field"),
    [(Product, "sku"), (Warehouse, "code")],
)
def test_code_is_unique_within_organization(model, code_field) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_a = uuid4()
    organization_b = uuid4()

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
                insert(model),
                [
                    {
                        "organization_id": organization_a,
                        code_field: "SHARED-001",
                        "name": "First item",
                    },
                    {
                        "organization_id": organization_b,
                        code_field: "SHARED-001",
                        "name": "Second item",
                    },
                ],
            )

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        insert(model).values(
                            organization_id=organization_a,
                            name="Duplicate item",
                            **{code_field: "SHARED-001"},
                        )
                    )
        finally:
            transaction.rollback()
