"""사용자 응답 만들기 (로그인·내 정보·슈퍼스쿨 API 공용)."""
from sqlmodel import Session, select

from app.models import SuperschoolAccount, User
from app.schemas import UserBrief, UserOut


def avatar_url(user: User) -> str | None:
    return f"/files/{user.avatar_path}" if user.avatar_path else None


def superschool_account(session: Session, user_id: int) -> SuperschoolAccount | None:
    return session.exec(select(SuperschoolAccount).where(SuperschoolAccount.user_id == user_id)).first()


def user_brief(session: Session, user: User) -> UserBrief:
    account = superschool_account(session, user.id)
    return UserBrief(id=user.id, login_id=user.login_id, name=user.name, role=user.role, avatar_url=avatar_url(user),
                     superschool_linked=account is not None, school=(account.school or None) if account else None)


def user_out(session: Session, user: User) -> UserOut:
    return UserOut(**user_brief(session, user).model_dump(), created_at=user.created_at)
