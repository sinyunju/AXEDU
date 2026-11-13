"""비밀번호 해시(bcrypt)와 JWT 발급/검증."""
import secrets
import string
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """유효하면 user_id, 아니면 None. (WebSocket 인증에서도 재사용)"""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


_INVITE_ALPHABET = string.ascii_uppercase + string.digits


def generate_invite_code(length: int = 6) -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(length))
