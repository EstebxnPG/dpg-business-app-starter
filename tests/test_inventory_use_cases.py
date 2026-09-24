from decimal import Decimal
from uuid import uuid4

import pytest

import app.modules.inventory.use_cases as inventory_use_cases
from app.core.authorization import (
    CurrentMembership,
    OrganizationNotFoundError,
    PermissionDeniedError,
)
from app.modules.inventory.service import MovementResult, MovementType
from app.modules.inventory.use_cases import (
    RecordManualMovementCommand,
    record_manual_stock_movement,
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
