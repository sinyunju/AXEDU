import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlmodel import select

from app.models import Role, SuperschoolAccount
from app.superschool import SchoolEvent, SuperschoolError, Tokens, get_superschool_client
from app.superschool.mock import MockSuperschool
from app.superschool.oauth import OAuthSuperschool
from tests.helpers import make_user

CB = "http://localhost:5173/auth/superschool/callback"


def code_body(code, redirect_uri=CB):
    return {"code": code, "redirect_uri": redirect_uri}


# ---------- start ----------
def test_start_redirects_to_mock_screen(client):
    r = client.get("/auth/superschool/start", params={"mode": "login", "redirect_uri": CB, "state": "s" * 16,
                                                      "role": "student"}, follow_redirects=False)
    assert r.status_code == 307
    loc = urlsplit(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == "http://localhost:5173/auth/superschool/mock"
    assert parse_qs(loc.query) == {"mode": ["login"], "state": ["s" * 16], "role": ["student"]}


@pytest.mark.parametrize("uri", [
    "https://evil.example/auth/superschool/callback",  # 등록 안 된 주소
    "http://localhost:5173/other",  # 콜백 경로가 아님
    "http://localhost:5173/auth/superschool/callback?x=1",
])
def test_start_rejects_unknown_redirect_uri(client, uri):
    r = client.get("/auth/superschool/start", params={"mode": "login", "redirect_uri": uri, "state": "s" * 16},
                   follow_redirects=False)
    assert r.status_code == 400
    assert client.post("/auth/superschool/callback", json=code_body("mock:student", uri)).status_code == 400


def test_start_validation(client):
    assert client.get("/auth/superschool/start", params={"mode": "x", "redirect_uri": CB, "state": "s" * 16},
                      follow_redirects=False).status_code == 422
    assert client.get("/auth/superschool/start", params={"mode": "login", "redirect_uri": CB, "state": "short"},
                      follow_redirects=False).status_code == 422


# ---------- 로그인 ----------
def test_login_creates_account_once_and_hides_tokens(client, session):
    r = client.post("/auth/superschool/callback", json=code_body("mock:student"))
    assert r.status_code == 200
    body = r.json()
    user = body["user"]
    assert user["name"] == "지우" and user["role"] == "student"
    assert user["superschool_linked"] is True and user["school"] == "천천중학교 2학년 3반"
    assert user["login_id"].startswith("ss_")
    assert "mock-token" not in r.text and "access_token" not in json.dumps(user)  # 슈퍼스쿨 토큰은 안 내려감
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert me["superschool_linked"] is True

    # 같은 슈퍼스쿨 계정으로 다시 로그인 → 같은 사용자
    again = client.post("/auth/superschool/callback", json=code_body("mock:student")).json()
    assert again["user"]["id"] == user["id"]
    assert len(session.exec(select(SuperschoolAccount)).all()) == 1

    teacher = client.post("/auth/superschool/callback", json=code_body("mock:teacher")).json()["user"]
    assert teacher["role"] == "teacher" and teacher["id"] != user["id"]


def test_login_bad_code(client):
    assert client.post("/auth/superschool/callback", json=code_body("wrong")).status_code == 400
    assert client.post("/auth/superschool/callback", json=code_body("mock:link")).status_code == 400  # 로그인엔 못 씀


# ---------- 연결 ----------
def test_link_then_login_with_superschool_and_unlink(client):
    u = make_user(client, "stu1", "student", name="이학생")
    r = client.post("/auth/superschool/link", json=code_body("mock:link"), headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["superschool_linked"] is True and r.json()["school"] == "천천중학교 2학년 3반"
    assert r.json()["name"] == "이학생"  # 내 이름은 그대로

    r = client.delete("/auth/superschool/link", headers=u["headers"])
    assert r.json()["superschool_linked"] is False and r.json()["school"] is None
    assert client.delete("/auth/superschool/link", headers=u["headers"]).status_code == 200  # 이미 해제돼도 OK


def test_link_conflicts_and_role_mismatch(client):
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")
    t1 = make_user(client, "tch1", "teacher")
    # 지우 계정이 이미 (슈퍼스쿨 로그인으로 생긴) 다른 사용자에 연결돼 있음
    client.post("/auth/superschool/callback", json=code_body("mock:student"))
    assert client.post("/auth/superschool/link", json=code_body("mock:student"),
                       headers=s1["headers"]).status_code == 409
    # 교사 계정에 학생 슈퍼스쿨 계정
    assert client.post("/auth/superschool/link", json=code_body("mock:student"),
                       headers=t1["headers"]).status_code in (400, 409)
    # 서로 다른 학생은 각자 연결 가능
    for u in (s1, s2):
        assert client.post("/auth/superschool/link", json=code_body("mock:link"), headers=u["headers"]).status_code == 200
    assert client.post("/auth/superschool/link", json=code_body("mock:link")).status_code == 401


def test_superschool_only_account_cannot_unlink(client):
    token = client.post("/auth/superschool/callback", json=code_body("mock:student")).json()["access_token"]
    assert client.delete("/auth/superschool/link", headers={"Authorization": f"Bearer {token}"}).status_code == 400


# ---------- 캘린더 ----------
def cal(client, user):
    today = date.today()
    return client.get("/calendar", params={"from": today.isoformat(), "to": (today + timedelta(days=30)).isoformat()},
                      headers=user["headers"]).json()


def test_calendar_includes_school_events_when_linked(client):
    u = make_user(client, "stu1", "student")
    before = cal(client, u)
    assert before["superschool_linked"] is False and before["events"] == []
    client.post("/auth/superschool/link", json=code_body("mock:link"), headers=u["headers"])
    after = cal(client, u)
    assert after["superschool_linked"] is True and after["superschool_error"] is None
    exam = next(e for e in after["events"] if e["category"] == "시험")
    assert exam["source"] == "superschool" and exam["id"].startswith("ss-") and exam["all_day"] is True
    assert exam["end"] > exam["start"]
    assert [e["start"] for e in after["events"]] == sorted(e["start"] for e in after["events"])


def test_calendar_survives_superschool_failure(client):
    u = make_user(client, "stu1", "student")
    client.post("/auth/superschool/link", json=code_body("mock:link"), headers=u["headers"])

    class Down(MockSuperschool):
        async def get_events(self, access_token, start, end):
            raise SuperschoolError("down")

    client.app.dependency_overrides[get_superschool_client] = lambda: Down()
    try:
        body = cal(client, u)
    finally:
        client.app.dependency_overrides.pop(get_superschool_client, None)
    assert body["superschool_linked"] is True and body["superschool_error"] and body["events"] == []


def test_expired_token_is_refreshed(client, session):
    u = make_user(client, "stu1", "student")
    client.post("/auth/superschool/link", json=code_body("mock:link"), headers=u["headers"])
    account = session.exec(select(SuperschoolAccount)).one()
    original = account.access_token
    account.token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    account.refresh_token = "r1"
    session.add(account)
    session.commit()
    seen = []

    class Refreshing(MockSuperschool):
        async def refresh(self, refresh_token):
            seen.append(refresh_token)
            return Tokens(original, "r2", datetime.now(timezone.utc) + timedelta(hours=1))

    client.app.dependency_overrides[get_superschool_client] = lambda: Refreshing()
    try:
        assert cal(client, u)["superschool_error"] is None
    finally:
        client.app.dependency_overrides.pop(get_superschool_client, None)
    assert seen == ["r1"]
    session.expire_all()
    assert session.exec(select(SuperschoolAccount)).one().refresh_token == "r2"


# ---------- 실제 OAuth 클라이언트 (가짜 응답으로) ----------
def oauth(handler):
    return OAuthSuperschool(client_id="cid", client_secret="secret", authorize_url="https://ss.example/oauth/authorize",
                            token_url="https://ss.example/oauth/token", api_base_url="https://api.ss.example/v1/",
                            scope="profile calendar", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_oauth_authorize_url():
    url = oauth(lambda r: httpx.Response(500)).authorize_url(redirect_uri=CB, state="st", mode="login", role=None)
    parts = urlsplit(url)
    assert url.startswith("https://ss.example/oauth/authorize?")
    assert parse_qs(parts.query) == {"response_type": ["code"], "client_id": ["cid"], "redirect_uri": [CB],
                                     "state": ["st"], "scope": ["profile calendar"]}
    assert "secret" not in url  # client_secret은 주소에 절대 안 들어감


def test_oauth_exchange_profile_events():
    requests = []

    def handler(req: httpx.Request):
        requests.append(req)
        if req.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
        assert req.headers["authorization"] == "Bearer AT"
        if req.url.path == "/v1/me":
            return httpx.Response(200, json={"id": 42, "name": "지우", "role": "student", "school_name": "천천중학교",
                                             "grade": 2, "class": 3})
        if req.url.path == "/v1/calendar":
            assert req.url.params["from"] == "2026-11-01" and req.url.params["to"] == "2026-11-30"
            return httpx.Response(200, json={"events": [
                {"id": "e1", "title": "기말고사", "start_date": "2026-11-20", "end_date": "2026-11-22", "category": "시험"},
                {"id": "e2", "title": "축제", "start_date": "2026-11-27T00:00:00+09:00", "end_date": "2026-11-27"},
            ]})
        return httpx.Response(404)

    c = oauth(handler)

    async def run():
        tokens = await c.exchange_code("CODE", CB)
        return tokens, await c.get_profile(tokens.access_token), await c.get_events(
            tokens.access_token, date(2026, 11, 1), date(2026, 11, 30))

    tokens, profile, events = asyncio.run(run())
    assert tokens.access_token == "AT" and tokens.refresh_token == "RT" and tokens.expires_at is not None
    form = parse_qs(requests[0].content.decode())
    assert form == {"grant_type": ["authorization_code"], "code": ["CODE"], "redirect_uri": [CB],
                    "client_id": ["cid"], "client_secret": ["secret"]}
    assert profile.superschool_id == "42" and profile.role == Role.student
    assert profile.school == "천천중학교 2학년 3반"
    assert events == [SchoolEvent("e1", "기말고사", date(2026, 11, 20), date(2026, 11, 22), "시험"),
                      SchoolEvent("e2", "축제", date(2026, 11, 27), None, "행사")]


@pytest.mark.parametrize("response", [
    httpx.Response(400, json={"error": "invalid_grant"}),
    httpx.Response(200, json={"token_type": "bearer"}),  # access_token 없음
    httpx.Response(200, text="<html>"),
])
def test_oauth_token_errors(response):
    with pytest.raises(SuperschoolError):
        asyncio.run(oauth(lambda r: response).exchange_code("CODE", CB))


def test_oauth_profile_errors():
    with pytest.raises(SuperschoolError):
        asyncio.run(oauth(lambda r: httpx.Response(401)).get_profile("AT"))
    with pytest.raises(SuperschoolError):
        asyncio.run(oauth(lambda r: httpx.Response(200, json={"id": 1, "name": "x", "role": "admin"})).get_profile("AT"))


def test_real_mode_requires_settings(tmp_env, monkeypatch):
    monkeypatch.setenv("SUPERSCHOOL_MOCK", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    get_superschool_client.cache_clear()
    with pytest.raises(RuntimeError, match="SUPERSCHOOL_CLIENT_ID"):
        get_superschool_client()
    for k, v in {"SUPERSCHOOL_CLIENT_ID": "a", "SUPERSCHOOL_CLIENT_SECRET": "b",
                 "SUPERSCHOOL_AUTHORIZE_URL": "https://x/a", "SUPERSCHOOL_TOKEN_URL": "https://x/t",
                 "SUPERSCHOOL_API_BASE_URL": "https://x/api"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    get_superschool_client.cache_clear()
    assert get_superschool_client().name == "oauth"
