from decimal import Decimal
from uuid import uuid4

import pytest

import app.modules.inventory.use_cases as inventory_use_cases
from app.core.authorization import (
    CurrentMembership,
    OrganizationNotFoundError,
    PermissionDeniedError,
)
from app.modules.inventory.service import MovementResult, MovementType, TransferResult
from app.modules.inventory.use_cases import (
    RecordManualMovementCommand,
    TransferInventoryCommand,
    record_manual_stock_movement,
    transfer_inventory,
)


def manual_command(organization_id, movement_type=MovementType.RECEIPT):
    return RecordManualMovementCommand(
        organization_id=organization_id,
        product_id=uuid4(),
        warehouse_id=uuid4(),
        movement_type=movement_type,
        quantity=Decimal("10"),
        reason="Supplier delivery",
        idempotency_key=str(uuid4()),
    )


def test_manual_movement_uses_authorized_member_as_actor(monkeypatch) -> None:
    organization_id = uuid4()
    user_id = uuid4()
    membership = CurrentMembership(
        organization_id=organization_id,
        user_id=user_id,
        role="warehouse_manager",
    )
    captured = {}
    expected = MovementResult(
        movement_id=uuid4(),
        balance=Decimal("10"),
        replayed=False,
    )

    def record(engine, command):
        captured["command"] = command
        return expected

    monkeypatch.setattr(inventory_use_cases, "record_stock_movement", record)

    result = record_manual_stock_movement(
        object(), membership, manual_command(organization_id)
    )

    assert result == expected
    assert captured["command"].performed_by_id == user_id


def test_salesperson_cannot_record_manual_movement(monkeypatch) -> None:
    organization_id = uuid4()
    membership = CurrentMembership(
        organization_id=organization_id,
        user_id=uuid4(),
        role="salesperson",
    )
    domain_called = False

    def record(engine, command):
        nonlocal domain_called
        domain_called = True

    monkeypatch.setattr(inventory_use_cases, "record_stock_movement", record)

    with pytest.raises(PermissionDeniedError):
        record_manual_stock_movement(
            object(), membership, manual_command(organization_id)
        )

    assert domain_called is False


def test_membership_cannot_be_reused_for_another_organization() -> None:
    membership = CurrentMembership(
        organization_id=uuid4(),
        user_id=uuid4(),
        role="admin",
    )

    with pytest.raises(OrganizationNotFoundError):
        record_manual_stock_movement(object(), membership, manual_command(uuid4()))


def test_transfer_uses_authorized_member_as_actor(monkeypatch) -> None:
    organization_id = uuid4()
    user_id = uuid4()
    membership = CurrentMembership(organization_id, user_id, "warehouse_manager")
    captured = {}
    expected = TransferResult(uuid4(), Decimal("7"), Decimal("3"), False)

    def transfer(engine, command):
        captured["command"] = command
        return expected

    monkeypatch.setattr(inventory_use_cases, "transfer_stock", transfer)
    result = transfer_inventory(
        object(),
        membership,
        TransferInventoryCommand(
            organization_id=organization_id,
            product_id=uuid4(),
            source_warehouse_id=uuid4(),
            destination_warehouse_id=uuid4(),
            quantity=Decimal("3"),
            reason="Store replenishment",
            idempotency_key="transfer-1",
        ),
    )

    assert result == expected
    assert captured["command"].performed_by_id == user_id


def test_salesperson_cannot_transfer_inventory(monkeypatch) -> None:
    organization_id = uuid4()
    membership = CurrentMembership(organization_id, uuid4(), "salesperson")
    command = TransferInventoryCommand(
        organization_id=organization_id,
        product_id=uuid4(),
        source_warehouse_id=uuid4(),
        destination_warehouse_id=uuid4(),
        quantity=Decimal("3"),
        reason="Store replenishment",
        idempotency_key="transfer-1",
    )

    with pytest.raises(PermissionDeniedError):
        transfer_inventory(object(), membership, command)
