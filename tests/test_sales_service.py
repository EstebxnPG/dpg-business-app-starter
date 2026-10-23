import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, update

from app.core.authorization import CurrentMembership
from app.core.security import hash_password
from app.modules.inventory.models import StockBalance, StockMovement
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.products.models import Product
from app.modules.sales.models import Sale, SaleLine
from app.modules.sales.service import (
    CreateSaleCommand,
    DiscountApprovalRequiredError,
    InvalidApprovalPinError,
    SaleApproval,
    SaleInsufficientStockError,
    SaleLineCommand,
    SalePriceBelowCostError,
    create_sale,
)
from app.modules.sales.use_cases import get_sale_receipt, list_sales
from app.modules.users.models import User
from app.modules.warehouses.models import Warehouse


def test_sales_preserve_prices_authorize_discounts_and_move_stock() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL")

    engine = create_engine(database_url)
    organization_id = uuid4()
    warehouse_id = uuid4()
    product_id = uuid4()
    second_product_id = uuid4()
    seller_id = uuid4()
    admin_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            insert(Organization).values(id=organization_id, name="Sales Test")
        )
        connection.execute(
            insert(User),
            [
                {
                    "id": seller_id,
                    "email": f"{seller_id}@example.com",
                    "password_hash": "unused",
                },
                {
                    "id": admin_id,
                    "email": f"{admin_id}@example.com",
                    "password_hash": "unused",
                },
            ],
        )
        connection.execute(
            insert(Membership),
            [
                {
                    "organization_id": organization_id,
                    "user_id": seller_id,
                    "role": "salesperson",
                    "approval_pin_hash": None,
                },
                {
                    "organization_id": organization_id,
                    "user_id": admin_id,
                    "role": "admin",
                    "approval_pin_hash": hash_password("123456"),
                },
            ],
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
            insert(Product),
            [
                {
                    "id": product_id,
                    "organization_id": organization_id,
                    "sku": "SALE-1",
                    "name": "Shampoo",
                    "cost": 12000,
                    "sale_price": 20000,
                },
                {
                    "id": second_product_id,
                    "organization_id": organization_id,
                    "sku": "SALE-2",
                    "name": "Conditioner",
                    "cost": 8000,
                    "sale_price": 15000,
                },
            ],
        )
        connection.execute(
            insert(StockBalance),
            [
                {
                    "organization_id": organization_id,
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": 20,
                },
                {
                    "organization_id": organization_id,
                    "product_id": second_product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": 1,
                },
            ],
        )

    def command(key, price=Decimal("20000"), approval=None, products=None):
        return CreateSaleCommand(
            organization_id=organization_id,
            warehouse_id=warehouse_id,
            sold_by_id=seller_id,
            seller_role="salesperson",
            lines=products or (SaleLineCommand(product_id, Decimal("2"), price),),
            discount_reason="Customer negotiation" if price < 20000 else None,
            approval=approval,
            idempotency_key=key,
        )

    try:
        concurrent_command = command("concurrent-sale")
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(
                executor.map(
                    lambda _: create_sale(engine, concurrent_command), range(6)
                )
            )
        created = next(result for result in results if not result.replayed)
        assert sum(not result.replayed for result in results) == 1
        assert {result.sale_id for result in results} == {created.sale_id}
        assert created.total == Decimal("40000")
        assert created.cost_total == Decimal("24000")

        discounted = create_sale(engine, command("policy-discount", Decimal("18000")))
        assert discounted.discount_total == Decimal("4000")
        assert discounted.approved_by_id is None

        with pytest.raises(DiscountApprovalRequiredError):
            create_sale(engine, command("approval-required", Decimal("17000")))
        with pytest.raises(InvalidApprovalPinError):
            create_sale(
                engine,
                command(
                    "wrong-pin", Decimal("17000"), SaleApproval(admin_id, "000000")
                ),
            )

        approved = create_sale(
            engine,
            command(
                "approved-discount", Decimal("17000"), SaleApproval(admin_id, "123456")
            ),
        )
        assert approved.approved_by_id == admin_id

        with pytest.raises(SalePriceBelowCostError):
            create_sale(engine, command("below-cost", Decimal("11000")))

        with engine.connect() as connection:
            before_failed_sale = connection.scalar(
                select(StockBalance.quantity).where(
                    StockBalance.organization_id == organization_id,
                    StockBalance.product_id == product_id,
                    StockBalance.warehouse_id == warehouse_id,
                )
            )
        with pytest.raises(SaleInsufficientStockError):
            create_sale(
                engine,
                command(
                    "atomic-failure",
                    products=(
                        SaleLineCommand(product_id, Decimal("1"), None),
                        SaleLineCommand(second_product_id, Decimal("2"), None),
                    ),
                ),
            )
        with engine.connect() as connection:
            after_failed_sale = connection.scalar(
                select(StockBalance.quantity).where(
                    StockBalance.organization_id == organization_id,
                    StockBalance.product_id == product_id,
                    StockBalance.warehouse_id == warehouse_id,
                )
            )
        assert after_failed_sale == before_failed_sale

        with engine.connect() as connection:
            line = connection.execute(
                select(
                    SaleLine.product_sku,
                    SaleLine.product_name,
                    SaleLine.list_unit_price,
                    SaleLine.unit_price,
                    SaleLine.unit_cost,
                ).where(SaleLine.sale_id == discounted.sale_id)
            ).one()
            movement_count = connection.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.sale_id == discounted.sale_id)
            )
        assert line.list_unit_price == Decimal("20000")
        assert line.unit_price == Decimal("18000")
        assert line.unit_cost == Decimal("12000")
        assert line.product_sku == "SALE-1"
        assert line.product_name == "Shampoo"
        assert movement_count == 1

        with engine.begin() as connection:
            connection.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(name="Renamed Shampoo", sale_price=Decimal("22000"))
            )
        membership = CurrentMembership(organization_id, seller_id, "salesperson")
        receipt = get_sale_receipt(engine, membership, discounted.sale_id)
        sales_page = list_sales(engine, membership, limit=2, cursor=None)

        assert receipt.lines[0].name == "Shampoo"
        assert receipt.lines[0].list_unit_price == Decimal("20000")
        assert len(sales_page.items) == 2
        assert sales_page.next_cursor is not None
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(StockMovement).where(
                    StockMovement.organization_id == organization_id
                )
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
            connection.execute(delete(User).where(User.id.in_([seller_id, admin_id])))
