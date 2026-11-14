"""실제 슈퍼스쿨 OAuth 클라이언트 (표준 OAuth 2.0 인가 코드 방식).

⚠️ 슈퍼스쿨 API 문서를 받지 못해 아래 주소·필드 이름은 가정한 것이다. 문서를 받으면 이 파일만 고치면 된다.
  - 로그인 화면:  GET  {SUPERSCHOOL_AUTHORIZE_URL}?response_type=code&client_id&redirect_uri&state&scope
  - 토큰 교환:    POST {SUPERSCHOOL_TOKEN_URL} (form: grant_type=authorization_code, code, redirect_uri,
                                                 client_id, client_secret)
                  → {access_token, refresh_token?, expires_in?}
  - 토큰 갱신:    POST {SUPERSCHOOL_TOKEN_URL} (form: grant_type=refresh_token, refresh_token, client_id, client_secret)
  - 내 정보:      GET  {SUPERSCHOOL_API_BASE_URL}/me  (Bearer)
                  → {id, name, role: "teacher"|"student", school_name, grade?, class?, subject?}
  - 학사 일정:    GET  {SUPERSCHOOL_API_BASE_URL}/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD  (Bearer)
                  → {events: [{id, title, start_date, end_date?, category}]}
client_secret과 슈퍼스쿨 토큰은 이 서버 안에서만 쓰고 프론트로 내려보내지 않는다.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.models import Role
from app.superschool.base import SchoolEvent, SuperschoolClient, SuperschoolError, SuperschoolProfile, Tokens

USER_AGENT = "rabbit-turtle-backend/0.1"


class OAuthSuperschool(SuperschoolClient):
    name = "oauth"

    def __init__(self, *, client_id: str, client_secret: str, authorize_url: str, token_url: str,
                 api_base_url: str, scope: str = "", timeout: float = 15,
                 http_client: httpx.AsyncClient | None = None):
        self.client_id, self.client_secret = client_id, client_secret
        self.authorize_endpoint, self.token_url = authorize_url, token_url
        self.api_base_url = api_base_url.rstrip("/")
        self.scope = scope
        self._http = http_client or httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def authorize_url(self, *, redirect_uri: str, state: str, mode: str, role: Role | None) -> str:
        query = {"response_type": "code", "client_id": self.client_id, "redirect_uri": redirect_uri, "state": state}
        if self.scope:
            query["scope"] = self.scope
        return f"{self.authorize_endpoint}?{urlencode(query)}"

    async def exchange_code(self, code: str, redirect_uri: str, *, role_hint: Role | None = None) -> Tokens:
        return await self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})

    async def refresh(self, refresh_token: str) -> Tokens:
        return await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def get_profile(self, access_token: str) -> SuperschoolProfile:
        return _profile(await self._get("/me", access_token))

    async def get_events(self, access_token: str, start: date, end: date) -> list[SchoolEvent]:
        data = await self._get("/calendar", access_token, {"from": start.isoformat(), "to": end.isoformat()})
        items = data.get("events") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise SuperschoolError("학사 일정 응답 형식이 올바르지 않습니다")
        return [_event(e) for e in items]

    # ---------- 내부 ----------
    async def _token(self, form: dict[str, str]) -> Tokens:
        form = {**form, "client_id": self.client_id, "client_secret": self.client_secret}
        try:
            r = await self._http.post(self.token_url, data=form, headers={"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise SuperschoolError(f"슈퍼스쿨 토큰 요청 실패: {e.__class__.__name__}") from e
        if r.status_code != 200:
            raise SuperschoolError(f"슈퍼스쿨 토큰 요청 거부 ({r.status_code})")  # 응답 본문은 남기지 않음 (토큰 노출 방지)
        d = _json(r)
        if not isinstance(d.get("access_token"), str) or not d["access_token"]:
            raise SuperschoolError("슈퍼스쿨 토큰 응답에 access_token이 없습니다")
        expires_in = d.get("expires_in")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                      if isinstance(expires_in, int | float) and expires_in > 0 else None)
        return Tokens(d["access_token"], d.get("refresh_token") or None, expires_at)

    async def _get(self, path: str, access_token: str, params: dict[str, str] | None = None) -> Any:
        try:
            r = await self._http.get(f"{self.api_base_url}{path}", params=params,
                                     headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
        except httpx.HTTPError as e:
            raise SuperschoolError(f"슈퍼스쿨 API 요청 실패: {e.__class__.__name__}") from e
        if r.status_code == 401:
            raise SuperschoolError("슈퍼스쿨 토큰이 만료되었거나 올바르지 않습니다")
        if r.status_code != 200:
            raise SuperschoolError(f"슈퍼스쿨 API 오류 ({r.status_code})")
        return _json(r)


def _json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError as e:
        raise SuperschoolError("슈퍼스쿨 응답이 JSON이 아닙니다") from e


def _profile(d: Any) -> SuperschoolProfile:
    """가정한 /me 응답 → 프로필. 실제 필드 이름이 다르면 여기만 고친다."""
    try:
        role = Role(d["role"])
        school = str(d.get("school_name") or "").strip()
        if role == Role.student and d.get("grade") and d.get("class"):
            school = f"{school} {d['grade']}학년 {d['class']}반".strip()
        elif role == Role.teacher and d.get("subject"):
            school = f"{school} · {d['subject']}".strip(" ·")
        return SuperschoolProfile(str(d["id"]), str(d["name"]).strip(), role, school)
    except (KeyError, TypeError, ValueError) as e:
        raise SuperschoolError("슈퍼스쿨 사용자 정보 형식이 올바르지 않습니다") from e


def _event(d: Any) -> SchoolEvent:
    """가정한 학사 일정 항목 → SchoolEvent."""
    try:
        start = date.fromisoformat(str(d["start_date"])[:10])
        end = date.fromisoformat(str(d["end_date"])[:10]) if d.get("end_date") else None
        return SchoolEvent(str(d["id"]), str(d["title"]), start, end if end and end != start else None,
                           str(d.get("category") or "행사"))
    except (KeyError, TypeError, ValueError) as e:
        raise SuperschoolError("슈퍼스쿨 학사 일정 형식이 올바르지 않습니다") from e
