import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import Engine, select

from app.database import get_engine
from app.modules.users.models import User

TOKEN_ISSUER = "dpg-business-app-starter"
TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30

password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash("not-a-real-password")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class InvalidCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def _secret_key() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")
    return secret


def authenticate_user(engine: Engine, email: str, password: str) -> CurrentUser:
    with engine.connect() as connection:
        user = connection.execute(
            select(User.id, User.email, User.password_hash).where(
                User.email == email.strip().lower(),
                User.active.is_(True),
            )
        ).one_or_none()

    if user is None:
        password_hasher.verify(password, dummy_password_hash)
        raise InvalidCredentialsError
    if not password_hasher.verify(password, user.password_hash):
        raise InvalidCredentialsError
    return CurrentUser(id=user.id, email=user.email)


def create_access_token(user: CurrentUser) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": expires,
            "iss": TOKEN_ISSUER,
        },
        _secret_key(),
        algorithm=TOKEN_ALGORITHM,
    )
    return token, TOKEN_EXPIRE_MINUTES * 60


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    engine: Engine = Depends(get_engine),
) -> CurrentUser:
    if token is None:
        raise InvalidCredentialsError

    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[TOKEN_ALGORITHM],
            issuer=TOKEN_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss"]},
        )
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise InvalidCredentialsError from None

    with engine.connect() as connection:
        user = connection.execute(
            select(User.id, User.email).where(
                User.id == user_id,
                User.active.is_(True),
            )
        ).one_or_none()
    if user is None:
        raise InvalidCredentialsError
    return CurrentUser(id=user.id, email=user.email)
