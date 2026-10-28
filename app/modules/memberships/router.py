from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.database import get_engine
from app.modules.memberships.schemas import MemberListResponse
from app.modules.memberships.use_cases import list_members

router = APIRouter(prefix="/organizations/{organization_id}/members", tags=["members"])


@router.get("", response_model=MemberListResponse)
def list_members_endpoint(
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> MemberListResponse:
    return MemberListResponse(
        items=[member.__dict__ for member in list_members(engine, membership)]
    )
