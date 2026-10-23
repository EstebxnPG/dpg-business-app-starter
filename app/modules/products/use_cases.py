from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.modules.inventory.models import StockBalance
from app.modules.products.models import Product


class ProductSkuConflictError(Exception):
    pass


class InvalidProductCursorError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class ProductHasStockError(Exception):
    pass


class ProductPriceBelowCostError(Exception):
    pass


@dataclass(frozen=True)
class ProductItem:
    id: UUID
    sku: str
    name: str
    cost: Decimal
    sale_price: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProductPage:
    items: list[ProductItem]
    next_cursor: UUID | None


def create_product(
    engine: Engine,
    membership: CurrentMembership,
    sku: str,
    name: str,
    cost: Decimal,
    sale_price: Decimal,
) -> ProductItem:
    require_permission(membership, Permission.CATALOG_MANAGE)
    try:
        with engine.begin() as connection:
            row = connection.execute(
                insert(Product)
                .values(
                    organization_id=membership.organization_id,
                    sku=sku.strip().upper(),
                    name=name.strip(),
                    cost=cost,
                    sale_price=sale_price,
                )
                .returning(
                    Product.id,
                    Product.sku,
                    Product.name,
                    Product.cost,
                    Product.sale_price,
                    Product.active,
                    Product.created_at,
                    Product.updated_at,
                )
            ).one()
    except IntegrityError as error:
        if error.orig.diag.constraint_name == "uq_products_organization_sku":
            raise ProductSkuConflictError from error
        raise
    return ProductItem(**row._mapping)


def list_products(
    engine: Engine,
    membership: CurrentMembership,
    limit: int,
    cursor: UUID | None,
    include_inactive: bool,
    search: str | None,
) -> ProductPage:
    require_permission(membership, Permission.INVENTORY_READ)
    filters = [Product.organization_id == membership.organization_id]
    if not include_inactive:
        filters.append(Product.active.is_(True))
    if search:
        escaped = (
            search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        filters.append(
            or_(
                Product.sku.ilike(pattern, escape="\\"),
                Product.name.ilike(pattern, escape="\\"),
            )
        )

    with engine.connect() as connection:
        if cursor is not None:
            cursor_row = connection.execute(
                select(Product.created_at, Product.id).where(
                    *filters, Product.id == cursor
                )
            ).one_or_none()
            if cursor_row is None:
                raise InvalidProductCursorError
            filters.append(
                or_(
                    Product.created_at > cursor_row.created_at,
                    and_(
                        Product.created_at == cursor_row.created_at,
                        Product.id > cursor_row.id,
                    ),
                )
            )

        rows = connection.execute(
            select(
                Product.id,
                Product.sku,
                Product.name,
                Product.cost,
                Product.sale_price,
                Product.active,
                Product.created_at,
                Product.updated_at,
            )
            .where(*filters)
            .order_by(Product.created_at, Product.id)
            .limit(limit + 1)
        ).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return ProductPage(
        items=[ProductItem(**row._mapping) for row in page_rows],
        next_cursor=page_rows[-1].id if has_more else None,
    )


def get_product(
    engine: Engine,
    membership: CurrentMembership,
    product_id: UUID,
) -> ProductItem:
    require_permission(membership, Permission.INVENTORY_READ)
    with engine.connect() as connection:
        row = connection.execute(
            select(
                Product.id,
                Product.sku,
                Product.name,
                Product.cost,
                Product.sale_price,
                Product.active,
                Product.created_at,
                Product.updated_at,
            ).where(
                Product.organization_id == membership.organization_id,
                Product.id == product_id,
            )
        ).one_or_none()
    if row is None:
        raise ProductNotFoundError
    return ProductItem(**row._mapping)


def update_product(
    engine: Engine,
    membership: CurrentMembership,
    product_id: UUID,
    name: str | None,
    active: bool | None,
    cost: Decimal | None,
    sale_price: Decimal | None,
) -> ProductItem:
    require_permission(membership, Permission.CATALOG_MANAGE)
    with engine.begin() as connection:
        current = connection.execute(
            select(Product.active, Product.cost, Product.sale_price)
            .where(
                Product.organization_id == membership.organization_id,
                Product.id == product_id,
            )
            .with_for_update()
        ).one_or_none()
        if current is None:
            raise ProductNotFoundError

        if active is False and current.active:
            quantity = connection.scalar(
                select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
                    StockBalance.organization_id == membership.organization_id,
                    StockBalance.product_id == product_id,
                )
            )
            if quantity > 0:
                raise ProductHasStockError

        values = {"updated_at": func.now()}
        if name is not None:
            values["name"] = name.strip()
        if active is not None:
            values["active"] = active
        effective_cost = cost if cost is not None else current.cost
        effective_sale_price = (
            sale_price if sale_price is not None else current.sale_price
        )
        if effective_sale_price < effective_cost:
            raise ProductPriceBelowCostError
        if cost is not None:
            values["cost"] = cost
        if sale_price is not None:
            values["sale_price"] = sale_price

        row = connection.execute(
            update(Product)
            .where(
                Product.organization_id == membership.organization_id,
                Product.id == product_id,
            )
            .values(**values)
            .returning(
                Product.id,
                Product.sku,
                Product.name,
                Product.cost,
                Product.sale_price,
                Product.active,
                Product.created_at,
                Product.updated_at,
            )
        ).one()
    return ProductItem(**row._mapping)
