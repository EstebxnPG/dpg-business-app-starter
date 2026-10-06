from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

OrganizationRole = Literal["admin", "warehouse_manager", "salesperson"]


class CreateInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: OrganizationRole

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Email is invalid")
        return normalized


class InvitationCreatedResponse(BaseModel):
    id: UUID
    email: str
    role: OrganizationRole
    expires_at: datetime
    acceptance_token: str


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class InvitationAcceptedResponse(BaseModel):
    organization_id: UUID
    user_id: UUID
    role: OrganizationRole
