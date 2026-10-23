import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership
from app.modules.inventory.models import StockBalance, StockMovement, StockTransfer
from app.modules.inventory.service import (
    IdempotencyConflictError,
    InactiveInventoryContextError,
    InsufficientStockError,
    MovementType,
    RecordMovementCommand,
    TransferStockCommand,
    record_stock_movement,
    transfer_stock,
)
from app.modules.inventory.use_cases import get_stock_position, list_stock_movements
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
    destination_warehouse_id = uuid4()
    user_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Inventory Test")
        )
        connection.execute(
            insert(User).values(
                id=user_id,
                email=f"{user_id}@example.com",
                password_hash="not-used-by-this-test",
            )
        )
        connection.execute(
            insert(Membership).values(
                organization_id=organization_id,
                user_id=user_id,
                role="warehouse_manager",
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
        connection.execute(
            insert(Warehouse).values(
                id=destination_warehouse_id,
                organization_id=organization_id,
                code="DESTINATION-WAREHOUSE",
                name="Destination Warehouse",
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
            idempotency_key=str(uuid4()),
        )

    try:
        receipt = record_stock_movement(engine, command(MovementType.RECEIPT, "10"))
        issue = record_stock_movement(engine, command(MovementType.ISSUE, "3"))

        assert receipt.balance == Decimal("10")
        assert issue.balance == Decimal("7")
        assert receipt.replayed is False
        assert issue.replayed is False

        repeated_issue = record_stock_movement(
            engine,
            issue_command := replace(
                command(MovementType.ISSUE, "3"),
                idempotency_key="repeated-issue",
            ),
        )
        replay = record_stock_movement(engine, issue_command)
        assert repeated_issue.balance == Decimal("4")
        assert replay == replace(repeated_issue, replayed=True)

        with pytest.raises(IdempotencyConflictError):
            record_stock_movement(
                engine,
                replace(issue_command, quantity=Decimal("2")),
            )

        concurrent_receipt = replace(
            command(MovementType.RECEIPT, "2"),
            idempotency_key="concurrent-receipt",
        )
        with ThreadPoolExecutor(max_workers=8) as executor:
            concurrent_results = list(
                executor.map(
                    lambda _: record_stock_movement(engine, concurrent_receipt),
                    range(8),
                )
            )

        assert {result.movement_id for result in concurrent_results} == {
            concurrent_results[0].movement_id
        }
        assert sum(not result.replayed for result in concurrent_results) == 1
        assert {result.balance for result in concurrent_results} == {Decimal("6")}

        transfer_command = TransferStockCommand(
            organization_id=organization_id,
            product_id=product_id,
            source_warehouse_id=warehouse_id,
            destination_warehouse_id=destination_warehouse_id,
            performed_by_id=user_id,
            quantity=Decimal("3"),
            reason="Store replenishment",
            idempotency_key="transfer-once",
        )
        with ThreadPoolExecutor(max_workers=8) as executor:
            transfer_results = list(
                executor.map(
                    lambda _: transfer_stock(engine, transfer_command), range(8)
                )
            )
        transfer = next(result for result in transfer_results if not result.replayed)
        transfer_replay = transfer_stock(engine, transfer_command)

        assert transfer.source_balance == Decimal("3")
        assert transfer.destination_balance == Decimal("3")
        assert transfer_replay == replace(transfer, replayed=True)
        assert {result.transfer_id for result in transfer_results} == {
            transfer.transfer_id
        }
        assert sum(not result.replayed for result in transfer_results) == 1

        with pytest.raises(IdempotencyConflictError):
            transfer_stock(engine, replace(transfer_command, quantity=Decimal("2")))

        with pytest.raises(InsufficientStockError):
            transfer_stock(
                engine,
                replace(
                    transfer_command,
                    quantity=Decimal("10"),
                    idempotency_key="transfer-too-much",
                ),
            )

        with engine.connect() as connection:
            linked_movements = connection.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.transfer_id == transfer.transfer_id)
            )
            transfer_count = connection.scalar(
                select(func.count())
                .select_from(StockTransfer)
                .where(StockTransfer.organization_id == organization_id)
            )

        assert linked_movements == 2
        assert transfer_count == 1

        with pytest.raises(InsufficientStockError):
            record_stock_movement(engine, command(MovementType.ISSUE, "8"))

        invalid_actor = replace(
            command(MovementType.RECEIPT, "5"), performed_by_id=uuid4()
        )
        with pytest.raises(IntegrityError):
            record_stock_movement(engine, invalid_actor)

        with engine.begin() as connection:
            connection.execute(
                update(Product).where(Product.id == product_id).values(active=False)
            )
        with pytest.raises(InactiveInventoryContextError):
            record_stock_movement(engine, command(MovementType.RECEIPT, "1"))
        with engine.begin() as connection:
            connection.execute(
                update(Product).where(Product.id == product_id).values(active=True)
            )

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

        assert balance == Decimal("3")
        assert movement_count == 6

        membership = CurrentMembership(
            organization_id=organization_id,
            user_id=user_id,
            role="warehouse_manager",
        )
        position = get_stock_position(engine, membership, product_id, warehouse_id)
        first_page = list_stock_movements(
            engine, membership, product_id, warehouse_id, limit=3, cursor=None
        )
        second_page = list_stock_movements(
            engine,
            membership,
            product_id,
            warehouse_id,
            limit=3,
            cursor=first_page.next_cursor,
        )

        assert position.quantity == Decimal("3")
        assert len(first_page.items) == 3
        assert first_page.next_cursor is not None
        assert len(second_page.items) == 2
        assert second_page.next_cursor is None
        assert len({item.id for item in first_page.items + second_page.items}) == 5
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(StockMovement).where(
                    StockMovement.organization_id == organization_id
                )
            )
            connection.execute(
                delete(StockTransfer).where(
                    StockTransfer.organization_id == organization_id
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
