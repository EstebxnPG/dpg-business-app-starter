from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, and_, insert, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.modules.products.models import Product


class ProductSkuConflictError(Exception):
    pass


class InvalidProductCursorError(Exception):
    pass


@dataclass(frozen=True)
class ProductItem:
    id: UUID
    sku: str
    name: str
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class ProductPage:
    items: list[ProductItem]
    next_cursor: UUID | None


def create_product(
    engine: Engine,
    membership: CurrentMembership,
    sku: str,
    name: str,
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
                )
                .returning(
                    Product.id,
                    Product.sku,
                    Product.name,
                    Product.active,
                    Product.created_at,
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
) -> ProductPage:
    require_permission(membership, Permission.INVENTORY_READ)
    filters = [Product.organization_id == membership.organization_id]
    if not include_inactive:
        filters.append(Product.active.is_(True))

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
                Product.active,
                Product.created_at,
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
