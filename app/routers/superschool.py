"""슈퍼스쿨 계정으로 로그인·계정 연결 (OAuth 2.0 인가 코드 방식).

흐름 (프론트 src/lib/superschool.ts, pages/auth/SuperschoolCallback.tsx)
  1) 프론트가 state를 만들어 저장하고 GET /auth/superschool/start?mode&redirect_uri&state 로 이동
  2) 백엔드가 슈퍼스쿨 로그인·동의 화면으로 redirect (목 모드: 프론트의 개발용 화면)
  3) 슈퍼스쿨이 redirect_uri?code&state 로 돌려보냄 → 프론트가 state를 확인 (다른 사이트가 끼어드는 것 방지)
  4) 프론트가 code를 POST /auth/superschool/callback(로그인) 또는 /link(연결)로 보냄
  5) 백엔드가 code를 토큰으로 바꾸고(client_secret 사용) 사용자 정보를 받아 계정을 찾거나 만든다
redirect_uri는 FRONTEND_ORIGINS에 있는 주소의 /auth/superschool/callback만 허용한다 (code가 엉뚱한 곳으로 가지 않게).
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import Role, SuperschoolAccount, User, utcnow
from app.schemas import LoginResponse, SuperschoolCodeRequest, UserOut
from app.security import create_access_token, hash_password
from app.services.users import superschool_account, user_brief, user_out
from app.superschool import SuperschoolClient, SuperschoolError, SuperschoolProfile, Tokens, get_superschool_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/superschool", tags=["superschool"])

CALLBACK_PATH = "/auth/superschool/callback"
CODE_FAILED = "슈퍼스쿨 인증에 실패했어요. 처음부터 다시 시도해 주세요"
UNAVAILABLE = "지금은 슈퍼스쿨에 연결할 수 없어요. 잠시 후 다시 시도해 주세요"


def _check_redirect_uri(uri: str) -> str:
    parts = urlsplit(uri)
    origin = f"{parts.scheme}://{parts.netloc}"
    if parts.path != CALLBACK_PATH or parts.query or parts.fragment or origin not in get_settings().cors_origins:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"redirect_uri는 FRONTEND_ORIGINS에 등록된 주소의 {CALLBACK_PATH}여야 합니다")
    return uri


async def _exchange(client: SuperschoolClient, body: SuperschoolCodeRequest,
                    role_hint: Role | None = None) -> tuple[Tokens, SuperschoolProfile]:
    redirect_uri = _check_redirect_uri(body.redirect_uri)
    try:
        tokens = await client.exchange_code(body.code, redirect_uri, role_hint=role_hint)
    except SuperschoolError as e:
        logger.info("슈퍼스쿨 code 교환 실패: %s", e)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CODE_FAILED)
    try:
        profile = await client.get_profile(tokens.access_token)
    except SuperschoolError as e:
        logger.warning("슈퍼스쿨 사용자 정보 실패: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
    return tokens, profile


def _save_tokens(account: SuperschoolAccount, tokens: Tokens, profile: SuperschoolProfile) -> None:
    account.school = profile.school
    account.access_token = tokens.access_token
    account.refresh_token = tokens.refresh_token or account.refresh_token
    account.token_expires_at = tokens.expires_at


@router.get("/start", summary="슈퍼스쿨 로그인·동의 화면으로 이동 (브라우저로 여는 주소)",
            response_class=RedirectResponse, status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            description="프론트가 window.location으로 이동시키는 주소. 슈퍼스쿨(목 모드는 프론트의 개발용 화면)로 redirect 한다. "
                        "state는 프론트가 만들어 보관했다가 돌아왔을 때 같은지 확인한다.")
def start(
    mode: Literal["login", "link"] = Query(),
    redirect_uri: str = Query(examples=["http://localhost:5173/auth/superschool/callback"]),
    state: str = Query(min_length=8, max_length=200),
    role: Role | None = Query(default=None, description="로그인 화면에서 누른 버튼 (교사·학생). 목 모드에서만 쓰임"),
    client: SuperschoolClient = Depends(get_superschool_client),
) -> RedirectResponse:
    url = client.authorize_url(redirect_uri=_check_redirect_uri(redirect_uri), state=state, mode=mode, role=role)
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post("/callback", response_model=LoginResponse, summary="슈퍼스쿨 계정으로 로그인 (없으면 계정 생성)",
             description="슈퍼스쿨 계정이 이미 연결된 사용자가 있으면 그 계정으로, 없으면 새 계정을 만들어 로그인한다. "
                         "새 계정은 비밀번호가 없어 슈퍼스쿨로만 로그인한다.")
async def callback(body: SuperschoolCodeRequest, session: Session = Depends(get_session),
                   client: SuperschoolClient = Depends(get_superschool_client)) -> LoginResponse:
    tokens, profile = await _exchange(client, body)
    account = session.exec(
        select(SuperschoolAccount).where(SuperschoolAccount.superschool_id == profile.superschool_id)
    ).first()
    if account is not None:
        user = session.get(User, account.user_id)
    else:
        user = User(login_id=f"ss_{secrets.token_hex(6)}", password_hash=hash_password(secrets.token_urlsafe(24)),
                    name=profile.name or "슈퍼스쿨 사용자", role=profile.role)
        session.add(user)
        session.flush()
        account = SuperschoolAccount(user_id=user.id, superschool_id=profile.superschool_id, access_token="")
    _save_tokens(account, tokens, profile)
    session.add(account)
    try:
        session.commit()
    except IntegrityError:  # 같은 슈퍼스쿨 계정으로 동시에 로그인
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "잠시 후 다시 시도해 주세요")
    session.refresh(user)
    return LoginResponse(access_token=create_access_token(user.id, user.role), user=user_brief(session, user))


@router.post("/link", response_model=UserOut, summary="로그인한 계정에 슈퍼스쿨 계정 연결",
             responses={400: {"description": "code 실패 또는 역할(교사·학생)이 다름"},
                        409: {"description": "그 슈퍼스쿨 계정이 이미 다른 계정에 연결됨"}})
async def link(body: SuperschoolCodeRequest, user: User = Depends(get_current_user),
               session: Session = Depends(get_session),
               client: SuperschoolClient = Depends(get_superschool_client)) -> UserOut:
    tokens, profile = await _exchange(client, body, role_hint=user.role)
    if profile.role != user.role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "역할(선생님·학생)이 다른 슈퍼스쿨 계정이에요")
    other = session.exec(
        select(SuperschoolAccount).where(SuperschoolAccount.superschool_id == profile.superschool_id)
    ).first()
    if other is not None and other.user_id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 슈퍼스쿨 계정은 이미 다른 계정에 연결되어 있어요")
    account = superschool_account(session, user.id)
    if account is None:
        account = SuperschoolAccount(user_id=user.id, superschool_id=profile.superschool_id, access_token="")
    else:
        account.superschool_id = profile.superschool_id  # 다른 슈퍼스쿨 계정으로 바꿔 연결
        account.linked_at = utcnow()
    _save_tokens(account, tokens, profile)
    session.add(account)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이 슈퍼스쿨 계정은 이미 다른 계정에 연결되어 있어요")
    return user_out(session, user)


@router.delete("/link", response_model=UserOut, summary="슈퍼스쿨 연결 해제",
               description="저장한 슈퍼스쿨 토큰도 함께 지운다. 슈퍼스쿨로만 가입한 계정은 비밀번호가 없어 해제하면 다시 로그인할 수 없으므로 거부한다.")
def unlink(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> UserOut:
    account = superschool_account(session, user.id)
    if account is not None:
        if user.login_id.startswith("ss_"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "슈퍼스쿨로 가입한 계정은 연결을 해제할 수 없어요 (다른 로그인 방법이 없어요)")
        session.delete(account)
        session.commit()
    return user_out(session, user)


async def valid_access_token(session: Session, account: SuperschoolAccount, client: SuperschoolClient) -> str:
    """만료됐으면 refresh_token으로 갱신해서 저장한 뒤 access_token을 돌려준다."""
    expires = account.token_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)  # SQLite는 시간대를 저장하지 않음
    if expires is None or expires > datetime.now(timezone.utc):
        return account.access_token
    if not account.refresh_token:
        raise SuperschoolError("슈퍼스쿨 토큰이 만료되었습니다")
    tokens = await client.refresh(account.refresh_token)
    account.access_token = tokens.access_token
    account.refresh_token = tokens.refresh_token or account.refresh_token
    account.token_expires_at = tokens.expires_at
    session.add(account)
    session.commit()
    return account.access_token
