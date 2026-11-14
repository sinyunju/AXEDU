from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.ai.base import image_extension
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import AvatarOut, LoginRequest, LoginResponse, PasswordChange, ProfileUpdate, SignupRequest, UserOut
from app.security import create_access_token, hash_password, verify_password
from app.services.users import avatar_url, user_brief, user_out
from app.storage import delete_file, save_file

router = APIRouter(prefix="/auth", tags=["auth"])

AVATAR_SUBDIR = "avatars"
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 프론트가 256px JPEG로 줄여 보내므로 넉넉함


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> UserOut:
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
    return user_out(session, user)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    user = session.exec(select(User).where(User.login_id == body.login_id)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    return LoginResponse(access_token=create_access_token(user.id, user.role), user=user_brief(session, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> UserOut:
    return user_out(session, user)


@router.patch("/me", response_model=UserOut, summary="내 정보 수정 (보낸 필드만)",
              description="`{name}`으로 이름 변경, `{avatar_url: null}`로 프로필 사진 삭제. 아이디·역할은 바꿀 수 없다.")
def update_me(body: ProfileUpdate, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)) -> UserOut:
    if body.name is not None:
        user.name = body.name
    old_avatar = None
    if "avatar_url" in body.model_fields_set:  # null을 명시적으로 보낸 경우만 삭제
        old_avatar, user.avatar_path = user.avatar_path, None
    session.add(user)
    session.commit()
    session.refresh(user)
    delete_file(old_avatar)
    return user_out(session, user)


@router.post("/me/avatar", response_model=AvatarOut, summary="프로필 사진 올리기",
             description="multipart `file` (JPEG/PNG/WebP, 2MB 이하). 예전 사진은 지운다. "
                         "사진 주소는 /files 아래라 로그인 없이 열리지만 파일명은 추측할 수 없는 UUID다.")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> AvatarOut:
    data = await file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "사진은 2MB 이하만 올릴 수 있어요")
    ext = image_extension(data)
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JPEG, PNG, WebP 사진만 올릴 수 있어요")
    old_avatar = user.avatar_path
    user.avatar_path = save_file(AVATAR_SUBDIR, data, ext)
    session.add(user)
    session.commit()
    delete_file(old_avatar)
    return AvatarOut(avatar_url=avatar_url(user))


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="비밀번호 변경",
             responses={400: {"description": "지금 비밀번호가 틀림"}})
def change_password(body: PasswordChange, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> Response:
    if not verify_password(body.current, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지금 비밀번호가 맞지 않아요")
    user.password_hash = hash_password(body.next)
    session.add(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
