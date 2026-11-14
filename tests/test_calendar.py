import pytest

from tests.helpers import make_pdf, make_user

PDF = make_pdf(["1쪽"])


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    t2 = make_user(client, "tch2", "teacher")
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")  # 미등록
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s1["headers"])

    def lesson(no, title, class_date=None):
        data = {"session_no": str(no), "title": title}
        if class_date:
            data["class_date"] = class_date
        return client.post(f"/courses/{course['id']}/lessons", data=data,
                           files={"file": ("a.pdf", PDF, "application/pdf")}, headers=t1["headers"]).json()["id"]

    ids = {
        "approved": lesson(1, "광합성", "2026-11-10"),
        "draft": lesson(2, "호흡", "2026-11-12"),
        "outside": lesson(3, "증산", "2026-12-05"),
        "nodate": lesson(4, "정리"),
    }
    for key in ("approved", "outside"):
        client.post(f"/lessons/{ids[key]}/generate", headers=t1["headers"])
        client.post(f"/lessons/{ids[key]}/approve", headers=t1["headers"])
    return {"t1": t1, "t2": t2, "s1": s1, "s2": s2, "ids": ids}


def get(client, user, frm="2026-11-01", to="2026-11-30"):
    return client.get("/calendar", params={"from": frm, "to": to}, headers=user["headers"])


def test_teacher_sees_all_dated_lessons_in_range(client, ctx):
    r = get(client, ctx["t1"])
    assert r.status_code == 200
    body = r.json()
    assert body["superschool_linked"] is False
    assert [e["lesson_id"] for e in body["events"]] == [ctx["ids"]["approved"], ctx["ids"]["draft"]]
    e = body["events"][0]
    assert e == {"id": f"lesson-{ctx['ids']['approved']}", "title": "과학 1회차 · 광합성", "start": "2026-11-10",
                 "end": None, "all_day": True, "source": "lesson", "category": None,
                 "lesson_id": ctx["ids"]["approved"], "lesson_status": "approved", "course_name": "과학"}
    assert get(client, ctx["t2"]).json()["events"] == []  # 다른 교사 과목은 안 보임


def test_student_sees_only_approved(client, ctx):
    assert [e["lesson_id"] for e in get(client, ctx["s1"]).json()["events"]] == [ctx["ids"]["approved"]]
    assert get(client, ctx["s2"]).json()["events"] == []  # 미등록


def test_range_parsing_and_validation(client, ctx):
    # ISO 날짜시간도 받음, 양 끝 포함
    r = get(client, ctx["t1"], "2026-11-10T00:00:00Z", "2026-11-12T23:59:59+09:00")
    assert len(r.json()["events"]) == 2
    assert len(get(client, ctx["t1"], "2026-11-11", "2026-11-11").json()["events"]) == 0
    assert get(client, ctx["t1"], "2026-11-30", "2026-11-01").status_code == 422
    assert get(client, ctx["t1"], "어제", "2026-11-01").status_code == 422
    assert get(client, ctx["t1"], "2026-01-01", "2027-12-31").status_code == 422
    assert client.get("/calendar", params={"from": "2026-11-01"}, headers=ctx["t1"]["headers"]).status_code == 422
    assert client.get("/calendar", params={"from": "2026-11-01", "to": "2026-11-30"}).status_code == 401
