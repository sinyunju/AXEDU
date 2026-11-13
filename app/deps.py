"""인증/권한 의존성."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.db import get_session
from app.models import Role, User
from app.security import decode_access_token

# auto_error=False: 토큰이 없을 때 403 대신 401을 직접 반환하기 위함
_bearer = HTTPBearer(auto_error=False, description="POST /auth/login 으로 받은 access_token")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise unauthorized
    user = session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.teacher:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "교사만 사용할 수 있습니다")
    return user


def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.student:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "학생만 사용할 수 있습니다")
    return user
