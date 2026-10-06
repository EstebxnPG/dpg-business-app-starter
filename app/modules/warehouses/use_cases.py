from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, and_, insert, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.authorization import CurrentMembership, Permission, require_permission
from app.modules.warehouses.models import Warehouse


class WarehouseCodeConflictError(Exception):
    pass


class InvalidWarehouseCursorError(Exception):
    pass


@dataclass(frozen=True)
class WarehouseItem:
    id: UUID
    code: str
    name: str
    active: bool
    created_at: datetime


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
) -> WarehousePage:
    require_permission(membership, Permission.INVENTORY_READ)
    filters = [Warehouse.organization_id == membership.organization_id]
    if not include_inactive:
        filters.append(Warehouse.active.is_(True))

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
