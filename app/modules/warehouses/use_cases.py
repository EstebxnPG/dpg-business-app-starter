from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.modules.inventory.models import StockBalance
from app.modules.warehouses.models import Warehouse


class WarehouseCodeConflictError(Exception):
    pass


class InvalidWarehouseCursorError(Exception):
    pass


class WarehouseNotFoundError(Exception):
    pass


class WarehouseHasStockError(Exception):
    pass


@dataclass(frozen=True)
class WarehouseItem:
    id: UUID
    code: str
    name: str
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WarehousePage:
    items: list[WarehouseItem]
    next_cursor: UUID | None


def create_warehouse(
    engine: Engine,
    membership: CurrentMembership,
    code: str,
    name: str,
) -> WarehouseItem:
    require_permission(membership, Permission.CATALOG_MANAGE)
    try:
        with engine.begin() as connection:
            row = connection.execute(
                insert(Warehouse)
                .values(
                    organization_id=membership.organization_id,
                    code=code.strip().upper(),
                    name=name.strip(),
                )
                .returning(
                    Warehouse.id,
                    Warehouse.code,
                    Warehouse.name,
                    Warehouse.active,
                    Warehouse.created_at,
                    Warehouse.updated_at,
                )
            ).one()
    except IntegrityError as error:
        if error.orig.diag.constraint_name == "uq_warehouses_organization_code":
            raise WarehouseCodeConflictError from error
        raise
    return WarehouseItem(**row._mapping)


def list_warehouses(
    engine: Engine,
    membership: CurrentMembership,
    limit: int,
    cursor: UUID | None,
    include_inactive: bool,
    search: str | None,
) -> WarehousePage:
    require_permission(membership, Permission.INVENTORY_READ)
    filters = [Warehouse.organization_id == membership.organization_id]
    if not include_inactive:
        filters.append(Warehouse.active.is_(True))
    if search:
        escaped = (
            search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        filters.append(
            or_(
                Warehouse.code.ilike(pattern, escape="\\"),
                Warehouse.name.ilike(pattern, escape="\\"),
            )
        )

    with engine.connect() as connection:
        if cursor is not None:
            cursor_row = connection.execute(
                select(Warehouse.created_at, Warehouse.id).where(
                    *filters, Warehouse.id == cursor
                )
            ).one_or_none()
            if cursor_row is None:
                raise InvalidWarehouseCursorError
            filters.append(
                or_(
                    Warehouse.created_at > cursor_row.created_at,
                    and_(
                        Warehouse.created_at == cursor_row.created_at,
                        Warehouse.id > cursor_row.id,
                    ),
                )
            )

        rows = connection.execute(
            select(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                Warehouse.active,
                Warehouse.created_at,
                Warehouse.updated_at,
            )
            .where(*filters)
            .order_by(Warehouse.created_at, Warehouse.id)
            .limit(limit + 1)
        ).all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return WarehousePage(
        items=[WarehouseItem(**row._mapping) for row in page_rows],
        next_cursor=page_rows[-1].id if has_more else None,
    )


def get_warehouse(
    engine: Engine,
    membership: CurrentMembership,
    warehouse_id: UUID,
) -> WarehouseItem:
    require_permission(membership, Permission.INVENTORY_READ)
    with engine.connect() as connection:
        row = connection.execute(
            select(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                Warehouse.active,
                Warehouse.created_at,
                Warehouse.updated_at,
            ).where(
                Warehouse.organization_id == membership.organization_id,
                Warehouse.id == warehouse_id,
            )
        ).one_or_none()
    if row is None:
        raise WarehouseNotFoundError
    return WarehouseItem(**row._mapping)


def update_warehouse(
    engine: Engine,
    membership: CurrentMembership,
    warehouse_id: UUID,
    name: str | None,
    active: bool | None,
) -> WarehouseItem:
    require_permission(membership, Permission.CATALOG_MANAGE)
    with engine.begin() as connection:
        current = connection.execute(
            select(Warehouse.active)
            .where(
                Warehouse.organization_id == membership.organization_id,
                Warehouse.id == warehouse_id,
            )
            .with_for_update()
        ).one_or_none()
        if current is None:
            raise WarehouseNotFoundError

        if active is False and current.active:
            quantity = connection.scalar(
                select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
                    StockBalance.organization_id == membership.organization_id,
                    StockBalance.warehouse_id == warehouse_id,
                )
            )
            if quantity > 0:
                raise WarehouseHasStockError

        values = {"updated_at": func.now()}
        if name is not None:
            values["name"] = name.strip()
        if active is not None:
            values["active"] = active

        row = connection.execute(
            update(Warehouse)
            .where(
                Warehouse.organization_id == membership.organization_id,
                Warehouse.id == warehouse_id,
            )
            .values(**values)
            .returning(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                Warehouse.active,
                Warehouse.created_at,
                Warehouse.updated_at,
            )
        ).one()
    return WarehouseItem(**row._mapping)
