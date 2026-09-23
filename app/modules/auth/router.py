from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from app.core.security import (
    CurrentUser,
    authenticate_user,
    create_access_token,
    get_current_user,
)
from app.database import get_engine
from app.modules.auth.schemas import CurrentUserResponse, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    engine: Annotated[Engine, Depends(get_engine)],
) -> TokenResponse:
    user = authenticate_user(engine, payload.email, payload.password)
    access_token, expires_in = create_access_token(user)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserResponse)
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(id=user.id, email=user.email)
