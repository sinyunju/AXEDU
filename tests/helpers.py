def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_user(client, login_id: str, role: str, name: str = "이름", password: str = "pass1234") -> dict:
    """가입 + 로그인 후 {id, headers} 반환."""
    r = client.post("/auth/signup", json={"login_id": login_id, "password": password, "name": name, "role": role})
    assert r.status_code == 201, r.text
    token = client.post("/auth/login", json={"login_id": login_id, "password": password}).json()["access_token"]
    return {"id": r.json()["id"], "headers": bearer(token)}
