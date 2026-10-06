from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.core.security import CurrentUser, get_optional_current_user
from app.database import get_engine
from app.modules.invitations.schemas import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    InvitationAcceptedResponse,
    InvitationCreatedResponse,
)
from app.modules.invitations.use_cases import (
    ExistingUserAuthenticationRequiredError,
    InvalidInvitationError,
    InvitationMembershipConflictError,
    accept_invitation,
    create_invitation,
)

router = APIRouter(tags=["invitations"])


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation_endpoint(
    payload: CreateInvitationRequest,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> InvitationCreatedResponse:
    invitation = create_invitation(engine, membership, payload.email, payload.role)
    return InvitationCreatedResponse(**invitation.__dict__)


@router.post(
    "/invitations/accept",
    response_model=InvitationAcceptedResponse,
)
def accept_invitation_endpoint(
    payload: AcceptInvitationRequest,
    request: Request,
    current_user: Annotated[CurrentUser | None, Depends(get_optional_current_user)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> InvitationAcceptedResponse | Response:
    try:
        accepted = accept_invitation(
            engine,
            payload.token,
            payload.password,
            current_user,
        )
    except InvalidInvitationError:
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVITATION_INVALID",
            message="The invitation is invalid, expired, or already used.",
        )
    except ExistingUserAuthenticationRequiredError:
        response = error_response(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVITATION_LOGIN_REQUIRED",
            message="Sign in with the invited account before accepting.",
        )
        response.headers["WWW-Authenticate"] = "Bearer"
        return response
    except InvitationMembershipConflictError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="MEMBERSHIP_ALREADY_EXISTS",
            message="The invited account already belongs to this organization.",
        )
    return InvitationAcceptedResponse(**accepted.__dict__)
