from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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


class TransferStockRequest(BaseModel):
    product_id: UUID
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    reason: str = Field(min_length=1, max_length=240)
    reference: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def warehouses_must_differ(self):
        if self.source_warehouse_id == self.destination_warehouse_id:
            raise ValueError("Source and destination warehouses must differ")
        return self


class StockTransferResponse(BaseModel):
    transfer_id: UUID
    source_balance: Decimal
    destination_balance: Decimal
    replayed: bool


class TransferHistoryItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    source_warehouse_id: UUID
    source_warehouse_name: str
    destination_warehouse_id: UUID
    destination_warehouse_name: str
    performed_by_id: UUID
    performed_by_email: str
    quantity: Decimal
    source_balance_after: Decimal
    destination_balance_after: Decimal
    reason: str
    reference: str | None
    created_at: datetime


class TransferHistoryResponse(BaseModel):
    items: list[TransferHistoryItemResponse]
    next_cursor: UUID | None


class StockBalanceResponse(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    quantity: Decimal
    damaged_quantity: Decimal


class MovementHistoryItemResponse(BaseModel):
    id: UUID
    performed_by_id: UUID
    movement_type: MovementType
    quantity: Decimal
    balance_after: Decimal
    reason: str
    reference: str | None
    stock_condition: str
    created_at: datetime


class MovementHistoryResponse(BaseModel):
    items: list[MovementHistoryItemResponse]
    next_cursor: UUID | None
