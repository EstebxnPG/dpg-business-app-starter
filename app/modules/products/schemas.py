from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateProductRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    cost: Decimal = Field(ge=0, max_digits=20, decimal_places=6)
    sale_price: Decimal = Field(ge=0, max_digits=20, decimal_places=6)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("SKU must not be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name must not be blank")
        return normalized

    @model_validator(mode="after")
    def price_must_cover_cost(self):
        if self.sale_price < self.cost:
            raise ValueError("Sale price must not be below cost")
        return self


class ProductResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    cost: Decimal
    sale_price: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


class UpdateProductRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    active: bool | None = None
    cost: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=6)
    sale_price: Decimal | None = Field(
        default=None, ge=0, max_digits=20, decimal_places=6
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self):
        if (
            self.name is None
            and self.active is None
            and self.cost is None
            and self.sale_price is None
        ):
            raise ValueError("At least one field must be provided")
        return self


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: UUID | None
