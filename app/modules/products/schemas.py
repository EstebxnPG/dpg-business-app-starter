from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateProductRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)

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


class ProductResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    active: bool
    created_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: UUID | None
