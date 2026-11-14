import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select

from app.deps import require_student, require_teacher
from app.models import Course, Enrollment, User


def signup(client, login_id="tch1", role="teacher", password="pass1234"):
    return client.post("/auth/signup", json={"login_id": login_id, "password": password, "name": "이름", "role": role})


def login(client, login_id="tch1", password="pass1234"):
    return client.post("/auth/login", json={"login_id": login_id, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_and_login_and_me(client):
    r = signup(client)
    assert r.status_code == 201
    body = r.json()
    assert body["login_id"] == "tch1" and body["role"] == "teacher"
    assert "password" not in body and "password_hash" not in body

    r = login(client)
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["user"] == {"id": body["id"], "login_id": "tch1", "name": "이름", "role": "teacher", "avatar_url": None}

    r = client.get("/auth/me", headers=bearer(data["access_token"]))
    assert r.status_code == 200 and r.json()["login_id"] == "tch1"


def test_password_is_hashed(client, session):
    signup(client)
    user = session.exec(select(User).where(User.login_id == "tch1")).one()
    assert user.password_hash != "pass1234" and user.password_hash.startswith("$2")


def test_duplicate_login_id(client):
    assert signup(client).status_code == 201
    r = signup(client)
    assert r.status_code == 409 and "detail" in r.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"login_id": "ab", "password": "pass1234", "name": "x", "role": "teacher"},  # 아이디 너무 짧음
        {"login_id": "tch1", "password": "pw", "name": "x", "role": "teacher"},  # 비번 너무 짧음
        {"login_id": "tch1", "password": "pass1234", "name": "x", "role": "admin"},  # 잘못된 역할
        {"login_id": "한글아이디", "password": "pass1234", "name": "x", "role": "teacher"},
    ],
)
def test_signup_validation(client, payload):
    assert client.post("/auth/signup", json=payload).status_code == 422


def test_wrong_password_and_unknown_user(client):
    signup(client)
    assert login(client, password="wrong").status_code == 401
    assert login(client, login_id="nobody").status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=bearer("garbage")).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    signup(client)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "jwt_expire_minutes", -1)
    token = login(client).json()["access_token"]
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_token_signed_with_other_secret_rejected(client):
    import jwt

    signup(client)
    forged = jwt.encode({"sub": "1", "role": "teacher"}, "other-secret-that-is-also-32-bytes-long-yyyy", algorithm="HS256")
    assert client.get("/auth/me", headers=bearer(forged)).status_code == 401


def test_role_dependencies(client):
    # 실제 앱과 같은 DB를 쓰는 별도 라우트로 require_teacher/require_student 검증
    app: FastAPI = client.app

    @app.get("/_t")
    def _t(u: User = Depends(require_teacher)):
        return {"ok": u.id}

    @app.get("/_s")
    def _s(u: User = Depends(require_student)):
        return {"ok": u.id}

    signup(client, "tch1", "teacher")
    signup(client, "stu1", "student")
    t = bearer(login(client, "tch1").json()["access_token"])
    s = bearer(login(client, "stu1").json()["access_token"])

    assert client.get("/_t", headers=t).status_code == 200
    assert client.get("/_t", headers=s).status_code == 403
    assert client.get("/_s", headers=s).status_code == 200
    assert client.get("/_s", headers=t).status_code == 403
    assert client.get("/_t").status_code == 401


def test_seed_is_idempotent_and_loginable(client, session):
    from scripts.seed import COURSE_INVITE_CODE, DEMO_PASSWORD, seed

    seed(session)
    seed(session)
    assert len(session.exec(select(User)).all()) == 4
    assert len(session.exec(select(Course)).all()) == 1
    assert len(session.exec(select(Enrollment)).all()) == 3
    assert session.exec(select(Course)).one().invite_code == COURSE_INVITE_CODE

    r = login(client, "teacher1", DEMO_PASSWORD)
    assert r.status_code == 200 and r.json()["user"]["role"] == "teacher"
    assert login(client, "student3", DEMO_PASSWORD).json()["user"]["role"] == "student"
