from uuid import UUID

from pydantic import BaseModel


class MemberResponse(BaseModel):
    user_id: UUID
    email: str
    role: str
    active: bool


class MemberListResponse(BaseModel):
    items: list[MemberResponse]
