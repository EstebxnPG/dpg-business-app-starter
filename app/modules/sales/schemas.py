from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class SaleLineRequest(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=20, decimal_places=6
    )


class DiscountApprovalRequest(BaseModel):
    approver_user_id: UUID
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CreateSaleRequest(BaseModel):
    warehouse_id: UUID
    lines: list[SaleLineRequest] = Field(min_length=1, max_length=100)
    discount_reason: str | None = Field(default=None, max_length=240)
    approval: DiscountApprovalRequest | None = None

    @field_validator("discount_reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def product_lines_must_be_unique(self):
        product_ids = [line.product_id for line in self.lines]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("A product may appear only once in a sale")
        return self


class SaleResponse(BaseModel):
    sale_id: UUID
    subtotal: Decimal
    discount_total: Decimal
    total: Decimal
    cost_total: Decimal
    approved_by_id: UUID | None
    replayed: bool


class UpdateSalesPolicyRequest(BaseModel):
    salesperson_max_discount_rate: Decimal = Field(
        ge=0, le=1, max_digits=5, decimal_places=4
    )


class SalesPolicyResponse(BaseModel):
    salesperson_max_discount_rate: Decimal


class SetApprovalPinRequest(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ApprovalPinResponse(BaseModel):
    configured: bool
