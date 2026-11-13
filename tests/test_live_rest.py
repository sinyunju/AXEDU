import pytest
from sqlmodel import select

from app.models import Lesson, LessonStatus, PageLive
from tests.helpers import make_pdf, make_user

PDF = make_pdf(["광합성이란? 식물이 빛으로 양분을 만드는 과정", "엽록체의 구조"])


@pytest.fixture()
def ctx(client):
    t1 = make_user(client, "tch1", "teacher")
    t2 = make_user(client, "tch2", "teacher")
    s1 = make_user(client, "stu1", "student")
    s2 = make_user(client, "stu2", "student")
    course = client.post("/courses", json={"name": "과학"}, headers=t1["headers"]).json()
    client.post("/courses/join", json={"invite_code": course["invite_code"]}, headers=s1["headers"])
    lesson_id = client.post(f"/courses/{course['id']}/lessons", data={"session_no": "1", "title": "광합성"},
                            files={"file": ("a.pdf", PDF, "application/pdf")}, headers=t1["headers"]).json()["id"]
    return {"t1": t1, "t2": t2, "s1": s1, "s2": s2, "course": course, "lesson_id": lesson_id}


def approve(client, ctx):
    h = ctx["t1"]["headers"]
    client.post(f"/lessons/{ctx['lesson_id']}/generate", headers=h)
    assert client.post(f"/lessons/{ctx['lesson_id']}/approve", headers=h).status_code == 200


def act(client, ctx, action, who="t1"):
    return client.post(f"/lessons/{ctx['lesson_id']}/{action}", headers=ctx[who]["headers"])


def set_page(session, lesson_id, page_no):
    lesson = session.get(Lesson, lesson_id)
    lesson.current_page = page_no
    session.add(lesson)
    session.commit()


# ---------- 시작 / 종료 ----------
def test_start_and_end(client, session, ctx):
    assert act(client, ctx, "start").status_code == 409  # 승인 전
    assert act(client, ctx, "end").status_code == 409  # 진행 중 아님
    approve(client, ctx)

    r = act(client, ctx, "start")
    assert r.status_code == 200 and r.json()["status"] == "live" and r.json()["current_page"] == 1
    assert act(client, ctx, "start").json()["status"] == "live"  # 이미 live → 그대로
    assert act(client, ctx, "approve").status_code == 409  # 수업 중 재승인 불가
    assert act(client, ctx, "generate").status_code == 409  # 수업 중 재생성 불가

    set_page(session, ctx["lesson_id"], 2)
    r = act(client, ctx, "end")
    assert r.status_code == 200 and r.json()["status"] == "ended"
    assert act(client, ctx, "end").json()["status"] == "ended"  # 이미 ended → 그대로

    # 재개: 페이지 유지
    r = act(client, ctx, "start")
    assert r.json()["status"] == "live" and r.json()["current_page"] == 2


def test_start_end_permissions(client, ctx):
    approve(client, ctx)
    for action in ("start", "end"):
        assert act(client, ctx, action, "t2").status_code == 403
        assert act(client, ctx, action, "s1").status_code == 403
        assert client.post(f"/lessons/9999/{action}", headers=ctx["t1"]["headers"]).status_code == 404


# ---------- 학생 페이지 조회 ----------
def page_url(ctx, n):
    return f"/lessons/{ctx['lesson_id']}/pages/{n}"


def test_page_view_permissions(client, ctx):
    assert client.get(page_url(ctx, 1), headers=ctx["s1"]["headers"]).status_code == 404  # 미승인 회차
    assert client.get(page_url(ctx, 1), headers=ctx["t1"]["headers"]).status_code == 200  # 교사는 미리보기 가능
    approve(client, ctx)
    assert client.get(page_url(ctx, 1), headers=ctx["s1"]["headers"]).status_code == 200
    assert client.get(page_url(ctx, 1), headers=ctx["s2"]["headers"]).status_code == 403  # 미등록
    assert client.get(page_url(ctx, 1), headers=ctx["t2"]["headers"]).status_code == 403  # 다른 교사
    assert client.get(page_url(ctx, 99), headers=ctx["s1"]["headers"]).status_code == 404
    assert client.get(page_url(ctx, 1)).status_code == 401


def test_page_view_content(client, session, ctx):
    approve(client, ctx)
    act(client, ctx, "start")
    h = ctx["s1"]["headers"]

    v = client.get(page_url(ctx, 1), headers=h).json()
    assert v["page_no"] == 1 and v["page_count"] == 2
    assert v["lesson_status"] == "live" and v["teacher_page"] == 1
    assert v["image_url"].startswith("/files/pages/")
    assert v["easy_sentences"] and v["hard_words"]
    assert v["easy_transcript"] == [] and v["transcript_updated_at"] is None
    assert "source_text" not in v and "image_suggestion" not in v

    # 선생님이 2쪽으로 이동 + 2쪽 자막이 쌓인 상태 (7단계 WebSocket이 할 일을 직접 재현)
    set_page(session, ctx["lesson_id"], 2)
    session.add(PageLive(lesson_id=ctx["lesson_id"], page_no=2, easy_transcript=["엽록체는 초록 알갱이예요."]))
    session.commit()

    v1 = client.get(page_url(ctx, 1), headers=h).json()  # 학생은 1쪽에 머물러도
    assert v1["teacher_page"] == 2 and v1["easy_transcript"] == []  # 선생님 위치는 알 수 있음
    v2 = client.get(page_url(ctx, 2), headers=h).json()
    assert v2["easy_transcript"] == ["엽록체는 초록 알갱이예요."] and v2["transcript_updated_at"]

    # 수업이 끝난 뒤에도 복습용으로 조회 가능
    act(client, ctx, "end")
    v2 = client.get(page_url(ctx, 2), headers=h).json()
    assert v2["lesson_status"] == "ended" and v2["easy_transcript"] == ["엽록체는 초록 알갱이예요."]


def test_live_and_ended_lessons_listed_for_students(client, ctx):
    approve(client, ctx)
    act(client, ctx, "start")
    lessons = client.get(f"/courses/{ctx['course']['id']}", headers=ctx["s1"]["headers"]).json()["lessons"]
    assert [(l["id"], l["status"]) for l in lessons] == [(ctx["lesson_id"], "live")]
