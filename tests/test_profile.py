import io

from tests.helpers import make_user

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def stored(tmp_path):
    d = tmp_path / "storage" / "avatars"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def test_update_name(client):
    u = make_user(client, "stu1", "student", name="이학생")
    r = client.patch("/auth/me", json={"name": "  박학생 "}, headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["name"] == "박학생" and r.json()["avatar_url"] is None and r.json()["login_id"] == "stu1"
    assert client.get("/auth/me", headers=u["headers"]).json()["name"] == "박학생"
    # 아무것도 안 보내면 그대로, 빈 이름·너무 긴 이름은 422, 아이디·역할은 무시
    assert client.patch("/auth/me", json={}, headers=u["headers"]).json()["name"] == "박학생"
    for bad in ({"name": "   "}, {"name": ""}, {"name": "가" * 51}, {"avatar_url": "/files/x.png"}):
        assert client.patch("/auth/me", json=bad, headers=u["headers"]).status_code == 422
    r = client.patch("/auth/me", json={"role": "teacher", "login_id": "x"}, headers=u["headers"])
    assert r.json()["role"] == "student" and r.json()["login_id"] == "stu1"
    assert client.patch("/auth/me", json={"name": "a"}).status_code == 401


def test_avatar_upload_replace_delete(client, tmp_path):
    u = make_user(client, "tch1", "teacher")
    r = client.post("/auth/me/avatar", files={"file": ("a.jpg", JPEG, "image/jpeg")}, headers=u["headers"])
    assert r.status_code == 200
    first = r.json()["avatar_url"]
    assert first.startswith("/files/avatars/") and first.endswith(".jpg")
    assert client.get(first).content == JPEG  # /files로 바로 열림
    # 로그인·내 정보에 avatar_url이 들어감
    assert client.get("/auth/me", headers=u["headers"]).json()["avatar_url"] == first
    login = client.post("/auth/login", json={"login_id": "tch1", "password": "pass1234"}).json()
    assert login["user"]["avatar_url"] == first

    # 새 사진 → 예전 파일 삭제
    second = client.post("/auth/me/avatar", files={"file": ("b.png", PNG, "image/png")},
                         headers=u["headers"]).json()["avatar_url"]
    assert second.endswith(".png") and stored(tmp_path) == [second.rsplit("/", 1)[1]]

    # 삭제
    r = client.patch("/auth/me", json={"avatar_url": None}, headers=u["headers"])
    assert r.json()["avatar_url"] is None and stored(tmp_path) == []
    # 이름만 바꿀 때는 사진이 지워지지 않음
    client.post("/auth/me/avatar", files={"file": ("a.jpg", JPEG, "image/jpeg")}, headers=u["headers"])
    assert client.patch("/auth/me", json={"name": "새이름"}, headers=u["headers"]).json()["avatar_url"]


def test_avatar_rejects_bad_files(client, tmp_path):
    u = make_user(client, "tch1", "teacher")
    r = client.post("/auth/me/avatar", files={"file": ("a.jpg", b"not an image", "image/jpeg")}, headers=u["headers"])
    assert r.status_code == 400
    big = JPEG + b"\x00" * (2 * 1024 * 1024)
    assert client.post("/auth/me/avatar", files={"file": ("a.jpg", io.BytesIO(big), "image/jpeg")},
                       headers=u["headers"]).status_code == 413
    assert stored(tmp_path) == []
    assert client.post("/auth/me/avatar", files={"file": ("a.jpg", JPEG, "image/jpeg")}).status_code == 401


def test_change_password(client):
    u = make_user(client, "stu1", "student")
    r = client.post("/auth/me/password", json={"current": "wrong", "next": "newpass1"}, headers=u["headers"])
    assert r.status_code == 400 and r.json() == {"detail": "지금 비밀번호가 맞지 않아요"}
    for bad in ({"current": "pass1234", "next": "abc"}, {"current": "pass1234", "next": "가" * 30}, {"current": "pass1234"}):
        assert client.post("/auth/me/password", json=bad, headers=u["headers"]).status_code == 422
    r = client.post("/auth/me/password", json={"current": "pass1234", "next": "newpass1"}, headers=u["headers"])
    assert r.status_code == 204 and r.content == b""
    assert client.post("/auth/login", json={"login_id": "stu1", "password": "pass1234"}).status_code == 401
    assert client.post("/auth/login", json={"login_id": "stu1", "password": "newpass1"}).status_code == 200
