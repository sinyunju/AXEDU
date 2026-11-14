import re

import pytest

from app.models import Lesson, LessonStatus
from tests.helpers import make_user


@pytest.fixture()
def users(client):
    return {
        "t1": make_user(client, "tch1", "teacher", "김선생"),
        "t2": make_user(client, "tch2", "teacher", "박선생"),
        "s1": make_user(client, "stu1", "student", "이학생"),
        "s2": make_user(client, "stu2", "student", "최학생"),
    }


def create_course(client, user, name="과학", description="설명"):
    r = client.post("/courses", json={"name": name, "description": description}, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def join(client, user, code):
    return client.post("/courses/join", json={"invite_code": code}, headers=user["headers"])


# ---------- 생성 ----------
def test_create_course(client, users):
    c = create_course(client, users["t1"])
    assert re.fullmatch(r"[A-Z0-9]{6}", c["invite_code"])
    assert c["teacher_id"] == users["t1"]["id"] and c["teacher_name"] == "김선생"


def test_create_course_requires_teacher(client, users):
    assert client.post("/courses", json={"name": "x"}, headers=users["s1"]["headers"]).status_code == 403
    assert client.post("/courses", json={"name": "x"}).status_code == 401
    assert client.post("/courses", json={"name": ""}, headers=users["t1"]["headers"]).status_code == 422


def test_invite_codes_are_unique_and_retry_on_collision(client, users, monkeypatch):
    codes = iter(["AAAAAA", "AAAAAA", "BBBBBB"])
    monkeypatch.setattr("app.routers.courses.generate_invite_code", lambda: next(codes))
    assert create_course(client, users["t1"])["invite_code"] == "AAAAAA"
    assert create_course(client, users["t1"])["invite_code"] == "BBBBBB"  # 충돌 후 재시도


# ---------- 목록 ----------
def test_list_courses_per_role(client, users):
    a = create_course(client, users["t1"], "A")
    create_course(client, users["t2"], "B")
    c = create_course(client, users["t1"], "C")

    names = [x["name"] for x in client.get("/courses", headers=users["t1"]["headers"]).json()]
    assert sorted(names) == ["A", "C"]

    assert client.get("/courses", headers=users["s1"]["headers"]).json() == []
    join(client, users["s1"], a["invite_code"])
    mine = client.get("/courses", headers=users["s1"]["headers"]).json()
    assert [x["id"] for x in mine] == [a["id"]]
    assert mine[0]["invite_code"] is None  # 학생에게는 초대 코드 숨김
    assert c["id"] not in [x["id"] for x in mine]


# ---------- 등록 ----------
def test_join_course(client, users):
    c = create_course(client, users["t1"])
    r = join(client, users["s1"], c["invite_code"].lower())  # 소문자도 허용
    assert r.status_code == 201
    assert r.json()["course"]["id"] == c["id"] and r.json()["course"]["invite_code"] is None


def test_join_errors(client, users):
    c = create_course(client, users["t1"])
    assert join(client, users["s1"], "ZZZZZZ").status_code == 404
    assert join(client, users["s1"], c["invite_code"]).status_code == 201
    assert join(client, users["s1"], c["invite_code"]).status_code == 409
    assert join(client, users["t2"], c["invite_code"]).status_code == 403  # 교사는 등록 불가
    assert join(client, users["s1"], "ABC").status_code == 422


# ---------- 상세 ----------
def test_course_detail_permissions(client, users):
    c = create_course(client, users["t1"])
    url = f"/courses/{c['id']}"
    assert client.get(url, headers=users["t1"]["headers"]).status_code == 200
    assert client.get(url, headers=users["t2"]["headers"]).status_code == 403  # 다른 교사
    assert client.get(url, headers=users["s1"]["headers"]).status_code == 403  # 미등록 학생
    assert client.get("/courses/9999", headers=users["t1"]["headers"]).status_code == 404
    assert client.get(url).status_code == 401

    join(client, users["s1"], c["invite_code"])
    assert client.get(url, headers=users["s1"]["headers"]).status_code == 200


def test_student_sees_only_approved_lessons(client, session, users):
    c = create_course(client, users["t1"])
    join(client, users["s1"], c["invite_code"])
    for no, st in enumerate(LessonStatus, start=1):  # 6가지 상태 각각 하나씩
        session.add(Lesson(course_id=c["id"], session_no=no, title=f"{no}회차", status=st))
    session.commit()

    teacher_view = client.get(f"/courses/{c['id']}", headers=users["t1"]["headers"]).json()
    assert [l["session_no"] for l in teacher_view["lessons"]] == [1, 2, 3, 4, 5, 6]

    student_view = client.get(f"/courses/{c['id']}", headers=users["s1"]["headers"]).json()
    assert {l["status"] for l in student_view["lessons"]} == {"approved", "live", "ended"}
    assert student_view["invite_code"] is None


# ---------- 학생 목록 ----------
def test_list_students(client, users):
    c = create_course(client, users["t1"])
    join(client, users["s1"], c["invite_code"])
    join(client, users["s2"], c["invite_code"])
    url = f"/courses/{c['id']}/students"

    r = client.get(url, headers=users["t1"]["headers"])
    assert r.status_code == 200
    assert [s["login_id"] for s in r.json()] == ["stu1", "stu2"]
    assert all("password_hash" not in s for s in r.json())

    assert client.get(url, headers=users["t2"]["headers"]).status_code == 403
    assert client.get(url, headers=users["s1"]["headers"]).status_code == 403
    assert client.get("/courses/9999/students", headers=users["t1"]["headers"]).status_code == 404


def test_lesson_count(client, session, users):
    c = create_course(client, users["t1"])
    assert c["lesson_count"] == 0
    join(client, users["s1"], c["invite_code"])
    for no, st in enumerate(LessonStatus, start=1):  # 6가지 상태 각각 하나씩
        session.add(Lesson(course_id=c["id"], session_no=no, title=f"{no}회차", status=st))
    session.commit()

    teacher = client.get("/courses", headers=users["t1"]["headers"]).json()
    assert teacher[0]["lesson_count"] == 6
    student = client.get("/courses", headers=users["s1"]["headers"]).json()
    assert student[0]["lesson_count"] == 3  # approved / live / ended만
    detail = client.get(f"/courses/{c['id']}", headers=users["s1"]["headers"]).json()
    assert detail["lesson_count"] == len(detail["lessons"]) == 3


# ---------- 과목 수정 ----------
def test_update_course(client):
    from tests.helpers import make_user

    t1 = make_user(client, "tchA", "teacher")
    t2 = make_user(client, "tchB", "teacher")
    s1 = make_user(client, "stuA", "student")
    c = client.post("/courses", json={"name": "과학", "description": "1반"}, headers=t1["headers"]).json()
    url = f"/courses/{c['id']}"

    r = client.patch(url, json={"name": "  생명과학 "}, headers=t1["headers"])
    assert r.status_code == 200
    assert r.json()["name"] == "생명과학" and r.json()["description"] == "1반"
    assert r.json()["invite_code"] == c["invite_code"]  # 초대 코드는 그대로
    r = client.patch(url, json={"description": "2학년 3반"}, headers=t1["headers"])
    assert r.json()["name"] == "생명과학" and r.json()["description"] == "2학년 3반"
    assert client.patch(url, json={"description": ""}, headers=t1["headers"]).json()["description"] == ""
    assert client.get(url, headers=t1["headers"]).json()["name"] == "생명과학"

    for bad in ({"name": "   "}, {"name": ""}, {"name": "가" * 101}, {"description": "가" * 1001}):
        assert client.patch(url, json=bad, headers=t1["headers"]).status_code == 422
    assert client.patch(url, json={"name": "x"}, headers=t2["headers"]).status_code == 403
    assert client.patch(url, json={"name": "x"}, headers=s1["headers"]).status_code == 403
    assert client.patch("/courses/9999", json={"name": "x"}, headers=t1["headers"]).status_code == 404
