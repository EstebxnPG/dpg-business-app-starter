from uuid import UUID

from pydantic import BaseModel


class OrganizationMembershipResponse(BaseModel):
    id: UUID
    name: str
    role: str
    active: bool


class OrganizationMembershipListResponse(BaseModel):
    items: list[OrganizationMembershipResponse]
