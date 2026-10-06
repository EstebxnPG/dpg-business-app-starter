from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.inventory.service import MovementType


class RecordMovementRequest(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    movement_type: MovementType
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    reason: str = Field(min_length=1, max_length=240)
    reference: str | None = Field(default=None, max_length=120)


class MovementResponse(BaseModel):
    movement_id: UUID
    balance: Decimal
    replayed: bool


class StockBalanceResponse(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    quantity: Decimal


class MovementHistoryItemResponse(BaseModel):
    id: UUID
    performed_by_id: UUID
    movement_type: MovementType
    quantity: Decimal
    balance_after: Decimal
    reason: str
    reference: str | None
    created_at: datetime


class MovementHistoryResponse(BaseModel):
    items: list[MovementHistoryItemResponse]
    next_cursor: UUID | None
