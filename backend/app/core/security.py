"""Password hashing (bcrypt) and JWT creation/validation.

Access and refresh tokens carry a `type` claim so one can never be used in
place of the other.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ACCESS = "access"
REFRESH = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _create_token(user_id: int, token_type: str, lifetime: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id, ACCESS, timedelta(minutes=get_settings().access_token_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id, REFRESH, timedelta(days=get_settings().refresh_token_days)
    )


def decode_token(token: str, expected_type: str) -> int:
    """Return the user id, or raise jwt.InvalidTokenError."""
    settings = get_settings()
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return int(payload["sub"])
