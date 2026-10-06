from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateWarehouseRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Code must not be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name must not be blank")
        return normalized


class WarehouseResponse(BaseModel):
    id: UUID
    code: str
    name: str
    active: bool
    created_at: datetime


class WarehouseListResponse(BaseModel):
    items: list[WarehouseResponse]
    next_cursor: UUID | None
