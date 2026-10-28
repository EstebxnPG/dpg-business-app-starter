from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from app.core.security import CurrentUser, get_current_user
from app.database import get_engine
from app.modules.organizations.schemas import OrganizationMembershipListResponse
from app.modules.organizations.use_cases import list_user_organizations

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=OrganizationMembershipListResponse)
def list_current_user_organizations(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> OrganizationMembershipListResponse:
    organizations = list_user_organizations(engine, current_user.id)
    return OrganizationMembershipListResponse(
        items=[organization.__dict__ for organization in organizations]
    )
