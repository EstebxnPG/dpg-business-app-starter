import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, insert, select

from app.core.authorization import CurrentMembership
from app.modules.inventory.models import StockBalance, StockMovement
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.sales.models import Sale, SaleLine, SaleReturn, SaleReturnLine
from app.modules.sales.returns_service import (
    ProcessSaleReturnCommand,
    RefundResolution,
    ReturnDisposition,
    ReturnKind,
    ReturnLineCommand,
    ReturnQuantityExceededError,
    SaleAlreadyAdjustedError,
    process_sale_return,
)
from app.modules.sales.use_cases import get_sale_receipt
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse


def test_returns_separate_sellable_and_damaged_stock() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_id = uuid4()
    warehouse_id = uuid4()
    product_id = uuid4()
    admin_id = uuid4()
    sale_id = uuid4()
    voidable_sale_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Return Test")
        )
        connection.execute(
            insert(User).values(
                id=admin_id,
                email=f"{admin_id}@example.com",
                password_hash="unused",
            )
        )
        connection.execute(
            insert(Membership).values(
                organization_id=organization_id, user_id=admin_id, role="admin"
            )
        )
        connection.execute(
            insert(Warehouse).values(
                id=warehouse_id,
                organization_id=organization_id,
                code="SHOP",
                name="Shop",
            )
        )
        connection.execute(
            insert(Product).values(
                id=product_id,
                organization_id=organization_id,
                sku="RETURN-1",
                name="Shampoo",
                cost=12000,
                sale_price=20000,
            )
        )
        connection.execute(
            insert(StockBalance).values(
                organization_id=organization_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                condition="AVAILABLE",
                quantity=7,
            )
        )
        for current_sale_id, quantity in ((sale_id, 2), (voidable_sale_id, 1)):
            connection.execute(
                insert(Sale).values(
                    id=current_sale_id,
                    organization_id=organization_id,
                    warehouse_id=warehouse_id,
                    sold_by_id=admin_id,
                    subtotal=Decimal("20000") * quantity,
                    discount_total=Decimal("2000") * quantity,
                    total=Decimal("18000") * quantity,
                    cost_total=Decimal("12000") * quantity,
                    idempotency_key=f"sale-{current_sale_id}",
                    request_fingerprint="a" * 64,
                )
            )
            connection.execute(
                insert(SaleLine).values(
                    sale_id=current_sale_id,
                    product_id=product_id,
                    organization_id=organization_id,
                    quantity=quantity,
                    product_sku="RETURN-1",
                    product_name="Shampoo",
                    list_unit_price=20000,
                    unit_price=18000,
                    unit_cost=12000,
                    line_total=Decimal("18000") * quantity,
                )
            )

    def return_command(key, disposition, resolution, quantity=Decimal("1")):
        return ProcessSaleReturnCommand(
            organization_id=organization_id,
            sale_id=sale_id,
            processed_by_id=admin_id,
            kind=ReturnKind.RETURN,
            refund_resolution=resolution,
            reason="Customer return",
            idempotency_key=key,
            lines=(ReturnLineCommand(product_id, quantity, disposition),),
        )

    try:
        damaged_command = return_command(
            "damaged-return",
            ReturnDisposition.DAMAGED,
            RefundResolution.REFUNDED_NOW,
        )
        with ThreadPoolExecutor(max_workers=6) as executor:
            damaged_results = list(
                executor.map(
                    lambda _: process_sale_return(engine, damaged_command), range(6)
                )
            )
        assert sum(not result.replayed for result in damaged_results) == 1
        assert len({result.sale_return_id for result in damaged_results}) == 1
        assert damaged_results[0].refunded_amount == Decimal("18000")

        no_refund = process_sale_return(
            engine,
            return_command(
                "restocked-no-refund",
                ReturnDisposition.RESTOCK,
                RefundResolution.NO_REFUND,
            ),
        )
        assert no_refund.return_value == Decimal("18000")
        assert no_refund.refunded_amount == Decimal("0")

        with pytest.raises(ReturnQuantityExceededError):
            process_sale_return(
                engine,
                return_command(
                    "too-many",
                    ReturnDisposition.RESTOCK,
                    RefundResolution.REFUNDED_NOW,
                ),
            )
        with pytest.raises(SaleAlreadyAdjustedError):
            process_sale_return(
                engine,
                ProcessSaleReturnCommand(
                    organization_id=organization_id,
                    sale_id=sale_id,
                    processed_by_id=admin_id,
                    kind=ReturnKind.VOID,
                    refund_resolution=RefundResolution.REFUNDED_NOW,
                    reason="Cannot void adjusted sale",
                    idempotency_key="invalid-void",
                ),
            )

        voided = process_sale_return(
            engine,
            ProcessSaleReturnCommand(
                organization_id=organization_id,
                sale_id=voidable_sale_id,
                processed_by_id=admin_id,
                kind=ReturnKind.VOID,
                refund_resolution=RefundResolution.REFUNDED_NOW,
                reason="Cashier error",
                idempotency_key="valid-void",
            ),
        )
        assert voided.return_value == Decimal("18000")

        with engine.connect() as connection:
            balances = dict(
                connection.execute(
                    select(StockBalance.condition, StockBalance.quantity).where(
                        StockBalance.organization_id == organization_id,
                        StockBalance.product_id == product_id,
                        StockBalance.warehouse_id == warehouse_id,
                    )
                ).all()
            )
            damaged_movement = connection.execute(
                select(
                    StockMovement.stock_condition,
                    StockMovement.sale_return_id,
                ).where(
                    StockMovement.organization_id == organization_id,
                    StockMovement.stock_condition == "DAMAGED",
                )
            ).one()

        assert balances == {
            "AVAILABLE": Decimal("9"),
            "DAMAGED": Decimal("1"),
        }
        assert damaged_movement.sale_return_id == damaged_results[0].sale_return_id

        receipt = get_sale_receipt(
            engine,
            CurrentMembership(organization_id, admin_id, "admin"),
            sale_id,
        )
        voided_receipt = get_sale_receipt(
            engine,
            CurrentMembership(organization_id, admin_id, "admin"),
            voidable_sale_id,
        )
        assert receipt.status == "RETURNED"
        assert len(receipt.adjustments) == 2
        assert voided_receipt.status == "VOIDED"
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(StockMovement).where(
                    StockMovement.organization_id == organization_id
                )
            )
            connection.execute(
                delete(SaleReturnLine).where(
                    SaleReturnLine.organization_id == organization_id
                )
            )
            connection.execute(
                delete(SaleReturn).where(SaleReturn.organization_id == organization_id)
            )
            connection.execute(
                delete(SaleLine).where(SaleLine.organization_id == organization_id)
            )
            connection.execute(
                delete(Sale).where(Sale.organization_id == organization_id)
            )
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
            connection.execute(delete(User).where(User.id == admin_id))
