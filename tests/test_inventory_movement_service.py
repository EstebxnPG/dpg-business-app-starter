import os
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.modules.inventory.models import StockBalance, StockMovement
from app.modules.inventory.service import (
    InsufficientStockError,
    MovementType,
    RecordMovementCommand,
    record_stock_movement,
)
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse


def test_movements_update_balance_and_history_atomically() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_id = uuid4()
    product_id = uuid4()
    warehouse_id = uuid4()
    user_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Inventory Test")
        )
        connection.execute(
            insert(User).values(id=user_id, email=f"{user_id}@example.com")
        )
        connection.execute(
            insert(Membership).values(
                organization_id=organization_id,
                user_id=user_id,
                role="operator",
            )
        )
        connection.execute(
            insert(Product).values(
                id=product_id,
                organization_id=organization_id,
                sku="TEST-PRODUCT",
                name="Test Product",
            )
        )
        connection.execute(
            insert(Warehouse).values(
                id=warehouse_id,
                organization_id=organization_id,
                code="TEST-WAREHOUSE",
                name="Test Warehouse",
            )
        )

    def command(movement_type: MovementType, quantity: str) -> RecordMovementCommand:
        return RecordMovementCommand(
            organization_id=organization_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            performed_by_id=user_id,
            movement_type=movement_type,
            quantity=Decimal(quantity),
            reason="Integration test",
        )

    try:
        receipt = record_stock_movement(engine, command(MovementType.RECEIPT, "10"))
        issue = record_stock_movement(engine, command(MovementType.ISSUE, "3"))

        assert receipt.balance == Decimal("10")
        assert issue.balance == Decimal("7")

        with pytest.raises(InsufficientStockError):
            record_stock_movement(engine, command(MovementType.ISSUE, "8"))

        invalid_actor = replace(
            command(MovementType.RECEIPT, "5"), performed_by_id=uuid4()
        )
        with pytest.raises(IntegrityError):
            record_stock_movement(engine, invalid_actor)

        with engine.connect() as connection:
            balance = connection.scalar(
                select(StockBalance.quantity).where(
                    StockBalance.organization_id == organization_id,
                    StockBalance.product_id == product_id,
                    StockBalance.warehouse_id == warehouse_id,
                )
            )
            movement_count = connection.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.organization_id == organization_id)
            )

        assert balance == Decimal("7")
        assert movement_count == 2
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(StockMovement).where(
                    StockMovement.organization_id == organization_id
                )
            )
            connection.execute(
                delete(StockBalance).where(
                    StockBalance.organization_id == organization_id
                )
            )
            connection.execute(
                delete(Membership).where(Membership.organization_id == organization_id)
            )
            connection.execute(
                delete(Product).where(Product.organization_id == organization_id)
            )
            connection.execute(
                delete(Warehouse).where(Warehouse.organization_id == organization_id)
            )
            connection.execute(
                delete(Organization).where(Organization.id == organization_id)
            )
            connection.execute(delete(User).where(User.id == user_id))
