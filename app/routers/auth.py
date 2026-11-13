from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginRequest, LoginResponse, SignupRequest, UserBrief, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> User:
    if session.exec(select(User).where(User.login_id == body.login_id)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다")
    user = User(
        login_id=body.login_id, password_hash=hash_password(body.password), name=body.name, role=body.role
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:  # 동시 가입 경합
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다")
    session.refresh(user)
    return user


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    user = session.exec(select(User).where(User.login_id == body.login_id)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    return LoginResponse(
        access_token=create_access_token(user.id, user.role),
        user=UserBrief(id=user.id, name=user.name, role=user.role),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
