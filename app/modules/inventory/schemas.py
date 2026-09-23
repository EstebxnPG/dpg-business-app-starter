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
